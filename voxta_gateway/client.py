"""
Gateway Client - A client library for downstream applications.

This module provides a ready-to-use client that handles all the complexity
of connecting to the Gateway, managing state, and processing events.

Usage:
    from voxta_gateway.client import GatewayClient

    client = GatewayClient("http://localhost:8081", "my-app")

    @client.on("dialogue_received")
    async def on_dialogue(data):
        print(f"Message: {data['text']}")

    await client.start()
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx
import websockets
from websockets.exceptions import ConnectionClosed


class ConnectionState(Enum):
    """Client connection state."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    READY = "ready"  # Connected AND chat is active


@dataclass
class GatewayState:
    """Local mirror of gateway state."""

    connected: bool = False
    chat_active: bool = False
    ai_state: str = "idle"
    current_speaker_id: str | None = None
    external_speaker_active: bool = False
    external_speaker_source: str | None = None
    characters: list[dict] = field(default_factory=list)

    def update_from_snapshot(self, snapshot: dict):
        """Update state from a gateway snapshot."""
        self.connected = snapshot.get("connected", False)
        self.chat_active = snapshot.get("chat_active", False)
        self.ai_state = snapshot.get("ai_state", "idle")
        self.current_speaker_id = snapshot.get("current_speaker_id")
        self.external_speaker_active = snapshot.get("external_speaker_active", False)
        self.external_speaker_source = snapshot.get("external_speaker_source")
        self.characters = snapshot.get("characters", [])


# Type alias for event handlers
EventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


class GatewayClient:
    """
    Client for connecting to and interacting with the Voxta Gateway.

    This client handles:
    - WebSocket connection with automatic reconnection
    - Event subscription and routing
    - State synchronization
    - High-level action methods (send_dialogue, etc.)

    Example:
        ```python
        client = GatewayClient(
            gateway_url="http://localhost:8081",
            client_id="my-app",
            events=["chat_started", "dialogue_received"]
        )

        @client.on("dialogue_received")
        async def handle_dialogue(data):
            print(f"Received: {data['text']}")

        # Run with automatic reconnection
        await client.start()
        ```
    """

    def __init__(
        self,
        gateway_url: str = "http://localhost:8081",
        client_id: str = "gateway-client",
        events: list[str] | None = None,
        filters: dict[str, list[str]] | None = None,
        reconnect_delay: float = 5.0,
        logger: logging.Logger | None = None,
    ):
        """
        Initialize the Gateway client.

        Args:
            gateway_url: HTTP URL of the gateway (ws:// derived automatically)
            client_id: Unique identifier for this client
            events: List of events to subscribe to (default: essential events)
            filters: Optional dictionary mapping event types to allowed sources
            reconnect_delay: Seconds to wait before reconnecting after disconnect
            logger: Optional logger instance
        """
        self.gateway_url = gateway_url.rstrip("/")
        self.client_id = client_id
        self.events = events or ["chat_started", "chat_closed", "ai_state_changed"]
        self.filters = filters or {}
        self.reconnect_delay = reconnect_delay
        self.logger = logger or logging.getLogger(f"GatewayClient.{client_id}")

        # Connection state
        self.connection_state = ConnectionState.DISCONNECTED
        self.state = GatewayState()

        # WebSocket
        self._websocket: websockets.WebSocketClientProtocol | None = None
        self._running = False
        self._listen_task: asyncio.Task | None = None

        # Event handlers
        self._handlers: dict[str, list[EventHandler]] = {}

        # HTTP client (reusable)
        self._http_client: httpx.AsyncClient | None = None

    # ─────────────────────────────────────────────────────────────
    # Event Registration
    # ─────────────────────────────────────────────────────────────

    def on(self, event_type: str, handler: EventHandler | None = None):
        """
        Register an event handler. Can be used as a decorator.

        Args:
            event_type: The event to listen for
            handler: The handler function (async or sync)

        Example:
            @client.on("dialogue_received")
            async def handle(data):
                print(data)

            # Or without decorator:
            client.on("dialogue_received", my_handler)
        """
        if handler is not None:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)
            return handler

        def decorator(func: EventHandler) -> EventHandler:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(func)
            return func

        return decorator

    def off(self, event_type: str, handler: EventHandler):
        """Remove an event handler."""
        if event_type in self._handlers:
            with contextlib.suppress(ValueError):
                self._handlers[event_type].remove(handler)

    # ─────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────

    async def start(self):
        """
        Start the client with automatic reconnection.

        This method runs indefinitely, maintaining the connection and
        reconnecting on failures. Use `stop()` to terminate.
        """
        self._running = True
        self._http_client = httpx.AsyncClient(base_url=self.gateway_url, timeout=30.0)

        while self._running:
            try:
                await self._connect()
                await self._listen()
            except ConnectionClosed as e:
                self.logger.warning(f"Connection closed: {e.code} {e.reason}")
            except Exception as e:
                self.logger.error(f"Connection error: {e}")

            # Reset state on disconnect
            self.connection_state = ConnectionState.DISCONNECTED
            self.state.chat_active = False
            await self._emit("disconnected", {})

            if self._running:
                self.logger.info(f"Reconnecting in {self.reconnect_delay}s...")
                await asyncio.sleep(self.reconnect_delay)

        if self._http_client:
            await self._http_client.aclose()

    async def stop(self):
        """Stop the client and close connections."""
        self._running = False

        if self._websocket:
            await self._websocket.close()
            self._websocket = None

        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def connect_once(self) -> bool:
        """
        Connect without automatic reconnection.

        Useful for one-shot operations or when you want manual control.

        Returns:
            True if connected successfully
        """
        self._http_client = httpx.AsyncClient(base_url=self.gateway_url, timeout=30.0)

        try:
            await self._connect()
            return True
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            return False

    async def _connect(self):
        """Establish WebSocket connection and subscribe."""
        self.connection_state = ConnectionState.CONNECTING
        self.logger.info(f"Connecting to {self.gateway_url}...")

        # Build WebSocket URL
        ws_url = self.gateway_url.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{ws_url}/ws"

        self._websocket = await websockets.connect(ws_url)

        # Subscribe to events
        subscription = {
            "type": "subscribe",
            "client_id": self.client_id,
            "events": self.events,
        }
        if self.filters:
            subscription["filters"] = self.filters

        await self._websocket.send(json.dumps(subscription))

        # Wait for snapshot
        response = await self._websocket.recv()
        msg = json.loads(response)

        if msg.get("type") == "snapshot":
            self.state.update_from_snapshot(msg["state"])
            self.connection_state = (
                ConnectionState.READY if self.state.chat_active else ConnectionState.CONNECTED
            )
            self.logger.info(
                f"Connected! Chat active: {self.state.chat_active}, AI state: {self.state.ai_state}"
            )
            await self._emit("connected", msg["state"])
        else:
            raise RuntimeError(f"Expected snapshot, got: {msg.get('type')}")

    async def _listen(self):
        """Listen for events from the gateway."""
        if not self._websocket:
            return

        async for message in self._websocket:
            event = json.loads(message)
            await self._handle_event(event)

    async def _handle_event(self, event: dict):
        """Process an incoming event."""
        event_type = event.get("type")
        data = event.get("data", {})

        # Update local state based on events
        if event_type == "chat_started":
            self.state.chat_active = True
            self.state.characters = data.get("characters", [])
            self.connection_state = ConnectionState.READY

        elif event_type == "chat_closed":
            self.state.chat_active = False
            self.state.characters = []
            self.connection_state = ConnectionState.CONNECTED

        elif event_type == "ai_state_changed":
            self.state.ai_state = data.get("new_state", "idle")

        elif event_type == "characters_updated":
            self.state.characters = data.get("characters", [])

        elif event_type == "external_speaker_started":
            self.state.external_speaker_active = True
            self.state.external_speaker_source = data.get("source")

        elif event_type == "external_speaker_stopped":
            self.state.external_speaker_active = False
            self.state.external_speaker_source = None

        elif event_type == "voxta_connected":
            self.state.connected = True

        elif event_type == "voxta_disconnected":
            self.state.connected = False

        # Emit to registered handlers
        await self._emit(event_type, data)

    async def _emit(self, event_type: str, data: dict):
        """Emit event to registered handlers."""
        if event_type not in self._handlers:
            return

        for handler in self._handlers[event_type]:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
            except Exception as e:
                self.logger.error(f"Error in handler for '{event_type}': {e}")

    # ─────────────────────────────────────────────────────────────
    # State Properties
    # ─────────────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        """Check if connected to the gateway."""
        return self.connection_state in [ConnectionState.CONNECTED, ConnectionState.READY]

    @property
    def is_ready(self) -> bool:
        """Check if ready to send messages (connected AND chat active)."""
        return self.connection_state == ConnectionState.READY

    @property
    def chat_active(self) -> bool:
        """Check if there's an active chat."""
        return self.state.chat_active

    @property
    def ai_state(self) -> str:
        """Get current AI state (idle, thinking, speaking)."""
        return self.state.ai_state

    @property
    def characters(self) -> list[dict]:
        """Get list of characters in the current chat."""
        return self.state.characters

    # ─────────────────────────────────────────────────────────────
    # Actions (HTTP)
    # ─────────────────────────────────────────────────────────────

    async def send_dialogue(
        self,
        text: str,
        source: str = "user",
        author: str | None = None,
        immediate_reply: bool | None = None,
    ) -> bool:
        """
        Send dialogue to the gateway.

        Args:
            text: The dialogue text
            source: Source of dialogue ("user", "game", "twitch")
            author: Optional author name
            immediate_reply: Whether AI should respond immediately

        Returns:
            True if sent successfully

        Raises:
            RuntimeError: If no active chat
        """
        if not self.state.chat_active:
            raise RuntimeError("Cannot send dialogue: no active chat")

        payload = {"text": text, "source": source}
        if author:
            payload["author"] = author
        if immediate_reply is not None:
            payload["immediate_reply"] = immediate_reply

        return await self._post("/dialogue", payload)

    async def send_context(
        self,
        key: str,
        content: str,
        description: str | None = None,
    ) -> bool:
        """
        Send context update to the gateway.

        Args:
            key: Unique key for this context type
            content: The context content
            description: Optional spoken summary

        Returns:
            True if sent successfully

        Raises:
            RuntimeError: If no active chat
        """
        if not self.state.chat_active:
            raise RuntimeError("Cannot send context: no active chat")

        payload = {"key": key, "content": content}
        if description:
            payload["description"] = description

        return await self._post("/context", payload)

    async def external_speaker_start(
        self,
        source: str,
        reason: str | None = None,
    ) -> bool:
        """
        Signal that an external speaker started talking.

        This interrupts the AI and prevents new responses until
        external_speaker_stop is called.

        Args:
            source: Who is speaking ("game", "user")
            reason: Optional reason for logging

        Returns:
            True if sent successfully
        """
        payload = {"source": source}
        if reason:
            payload["reason"] = reason

        return await self._post("/external_speaker_start", payload)

    async def external_speaker_stop(self, trigger_response: bool = True) -> bool:
        """
        Signal that external speaker stopped talking.

        Args:
            trigger_response: Should AI respond after release?

        Returns:
            True if sent successfully
        """
        return await self._post("/external_speaker_stop", {"trigger_response": trigger_response})

    async def tts_playback_start(
        self,
        character_id: str,
        message_id: str | None = None,
    ) -> bool:
        """
        Signal that TTS playback started.

        Args:
            character_id: Which character is speaking
            message_id: Which message is being spoken

        Returns:
            True if sent successfully
        """
        payload = {"character_id": character_id}
        if message_id:
            payload["message_id"] = message_id

        return await self._post("/tts_playback_start", payload)

    async def tts_playback_complete(
        self,
        character_id: str,
        message_id: str | None = None,
    ) -> bool:
        """
        Signal that TTS playback finished.

        Args:
            character_id: Which character finished speaking
            message_id: Which message was spoken

        Returns:
            True if sent successfully
        """
        payload = {"character_id": character_id}
        if message_id:
            payload["message_id"] = message_id

        return await self._post("/tts_playback_complete", payload)

    async def get_state(self) -> dict:
        """
        Fetch current state from the gateway.

        Returns:
            State dictionary
        """
        if not self._http_client:
            self._http_client = httpx.AsyncClient(base_url=self.gateway_url, timeout=30.0)

        response = await self._http_client.get("/state")
        response.raise_for_status()
        return response.json()

    async def health_check(self) -> dict:
        """
        Check gateway health.

        Returns:
            Health status dictionary
        """
        if not self._http_client:
            self._http_client = httpx.AsyncClient(base_url=self.gateway_url, timeout=30.0)

        response = await self._http_client.get("/health")
        response.raise_for_status()
        return response.json()

    async def _post(self, endpoint: str, payload: dict) -> bool:
        """Send a POST request to the gateway."""
        if not self._http_client:
            self._http_client = httpx.AsyncClient(base_url=self.gateway_url, timeout=30.0)

        try:
            response = await self._http_client.post(endpoint, json=payload)
            response.raise_for_status()
            return True
        except Exception as e:
            self.logger.error(f"POST {endpoint} failed: {e}")
            return False

    # ─────────────────────────────────────────────────────────────
    # Utility Methods
    # ─────────────────────────────────────────────────────────────

    async def wait_for_chat(self, timeout: float = 30.0) -> bool:
        """
        Wait until a chat becomes active.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if chat became active, False if timeout
        """
        if self.state.chat_active:
            return True

        event = asyncio.Event()

        async def on_chat_started(_):
            event.set()

        self.on("chat_started", on_chat_started)

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            self.off("chat_started", on_chat_started)

    async def wait_for_idle(self, timeout: float = 30.0) -> bool:
        """
        Wait until AI state becomes idle.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if AI became idle, False if timeout
        """
        if self.state.ai_state == "idle":
            return True

        event = asyncio.Event()

        async def on_state_changed(data):
            if data.get("new_state") == "idle":
                event.set()

        self.on("ai_state_changed", on_state_changed)

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            self.off("ai_state_changed", on_state_changed)
