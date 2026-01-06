"""
Gateway - Core orchestration class with high-level semantic actions.

This module contains the main Gateway class that ties together all components
and provides the high-level API that downstream applications use. It translates
semantic actions into Voxta operations.
"""

import logging
from typing import Any

from voxta_gateway.event_emitter import EventEmitter
from voxta_gateway.sentence_buffer import SentenceBuffer
from voxta_gateway.state import AIState, GatewayState
from voxta_gateway.voxta_bridge import VoxtaBridge
from voxta_gateway.websocket_manager import WebSocketManager


class Gateway:
    """
    Central Gateway class that orchestrates all components.

    The Gateway provides high-level semantic APIs that hide Voxta internals
    from downstream applications. It:

    1. Maintains mirrored state through VoxtaBridge
    2. Processes reply chunks into sentences via SentenceBuffer
    3. Broadcasts events to subscribed clients via WebSocketManager
    4. Translates high-level actions into Voxta operations

    Important: The Gateway never makes autonomous decisions based on state.
    All actions are triggered by API calls from downstream apps.
    """

    def __init__(
        self,
        voxta_url: str,
        logger: logging.Logger | None = None,
    ):
        self.logger = logger or logging.getLogger("Gateway")

        # Core components
        self.state = GatewayState()
        self.event_emitter = EventEmitter(self.logger.getChild("Events"))
        self.ws_manager = WebSocketManager(self.logger.getChild("WebSocket"))

        # Voxta connection
        self.bridge = VoxtaBridge(
            voxta_url=voxta_url,
            state=self.state,
            event_emitter=self.event_emitter,
            logger=self.logger.getChild("Bridge"),
        )

        # Sentence processing
        self.sentence_buffer = SentenceBuffer(on_sentence=self._on_sentence_ready)

        # Wire up internal event routing
        self._setup_event_routing()

    def _setup_event_routing(self):
        """Set up routing from internal events to WebSocket broadcasts."""
        # Route events from VoxtaBridge to WebSocket clients
        events_to_broadcast = [
            "ai_state_changed",
            "dialogue_received",
            "characters_updated",
            "app_trigger",
            "external_speaker_started",
            "external_speaker_stopped",
            "voxta_connected",
            "voxta_disconnected",
            "chat_started",
            "chat_closed",
        ]

        for event_name in events_to_broadcast:
            self.event_emitter.on(event_name, self._make_broadcaster(event_name))

        # Route reply chunks to sentence buffer
        self.event_emitter.on("reply_chunk", self._handle_reply_chunk)
        self.event_emitter.on("reply_end", self._handle_reply_end)
        self.event_emitter.on("reply_cancelled", self._handle_reply_cancelled)

    def _make_broadcaster(self, event_name: str):
        """Create a broadcast handler for an event type."""

        async def broadcast_handler(data: dict):
            await self.ws_manager.broadcast(event_name, data)

        return broadcast_handler

    async def _handle_reply_chunk(self, data: dict):
        """Process reply chunks through sentence buffer."""
        await self.sentence_buffer.process_chunk(
            message_id=data["message_id"],
            character_id=data["character_id"],
            text=data["text"],
            start_index=data.get("start_index", 0),
        )

    async def _handle_reply_end(self, data: dict):
        """Flush sentence buffer when reply ends."""
        message_id = data.get("message_id")
        if message_id:
            await self.sentence_buffer.flush(message_id)

    async def _handle_reply_cancelled(self, data: dict):
        """Clear sentence buffer when reply is cancelled."""
        message_id = data.get("message_id")
        if message_id:
            self.sentence_buffer.clear(message_id)

    async def _on_sentence_ready(self, text: str, character_id: str, message_id: str):
        """Called by SentenceBuffer when a complete sentence is ready."""
        await self.ws_manager.broadcast(
            "sentence_ready",
            {
                "text": text,
                "character_id": character_id,
                "message_id": message_id,
            },
        )

    # ─────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────

    async def start(self):
        """Start the gateway and connect to Voxta."""
        self.logger.info("Starting Gateway...")
        await self.bridge.start()

    async def stop(self):
        """Stop the gateway and disconnect from Voxta."""
        self.logger.info("Stopping Gateway...")
        await self.bridge.stop()

    # ─────────────────────────────────────────────────────────────
    # High-Level Semantic APIs
    # ─────────────────────────────────────────────────────────────

    async def external_speaker_start(self, source: str, reason: str | None = None):
        """
        Signal that an external speaker (game NPC, user) started talking.

        This interrupts the AI if it's speaking or thinking and puts the
        system in a "busy" state until external_speaker_stop is called.

        Args:
            source: Who is speaking ("game", "user", etc.)
            reason: Optional reason for the interrupt
        """
        if self.state.external_speaker_active:
            self.logger.debug(
                f"External speaker already active: {self.state.external_speaker_source}"
            )
            return

        self.logger.info(f"External speaker started: {source} (reason: {reason})")

        # Update state
        self.state.external_speaker_active = True
        self.state.external_speaker_source = source

        # If AI is currently speaking or thinking, interrupt it
        if self.state.ai_state in [AIState.SPEAKING, AIState.THINKING]:
            await self.bridge.interrupt()

        # Tell Voxta we're "busy" by sending speech_playback_start
        # This prevents Voxta from generating more responses
        if self.state.last_message_id:
            await self.bridge.speech_playback_start(self.state.last_message_id)

        # Notify downstream apps
        await self.event_emitter.emit(
            "external_speaker_started",
            {"source": source, "reason": reason},
        )

    async def external_speaker_stop(self, trigger_response: bool = True):
        """
        Signal that external speaker stopped talking.

        This releases the "busy" state and optionally triggers the AI
        to respond to any accumulated context.

        Args:
            trigger_response: If True, request AI to respond after release
        """
        if not self.state.external_speaker_active:
            self.logger.debug("External speaker not active, ignoring stop")
            return

        source = self.state.external_speaker_source
        self.logger.info(f"External speaker stopped: {source}")

        # Update state
        self.state.external_speaker_active = False
        self.state.external_speaker_source = None

        # Tell Voxta we're ready again
        if self.state.last_message_id:
            await self.bridge.speech_playback_complete(self.state.last_message_id)

        # Optionally trigger AI to respond
        if trigger_response and self.state.characters:
            char_id = self.state.get_first_character_id()
            if char_id:
                await self.bridge.character_speech_request(char_id)

        # Notify downstream apps
        await self.event_emitter.emit("external_speaker_stopped", {"source": source})

    async def send_dialogue(
        self,
        text: str,
        source: str,
        author: str | None = None,
        immediate_reply: bool | None = None,
    ):
        """
        Send dialogue that should appear in chat and potentially trigger AI response.

        Args:
            text: The dialogue text
            source: Where this came from ("user", "game", "twitch")
            author: Optional author name (e.g., Twitch username)
            immediate_reply: Whether AI should respond immediately.
                            Defaults based on source (True for "user")
        """
        # Default immediate_reply based on source
        if immediate_reply is None:
            immediate_reply = source == "user"

        # Format message with attribution if needed
        if author and source in ["game", "twitch"]:
            formatted = f"[{source.upper()}] {author}: {text}"
        elif source != "user":
            formatted = f"[{source.upper()}] {text}"
        else:
            formatted = text

        self.logger.info(f"Sending dialogue ({source}): {text[:50]}...")

        # Send to Voxta
        await self.bridge.send_message(
            text=formatted,
            do_reply=immediate_reply,
            do_user_inference=source == "user",
            do_character_inference=immediate_reply,
        )

        # Broadcast to dialogue subscribers (chat overlay)
        await self.event_emitter.emit(
            "dialogue_received",
            {
                "text": text,
                "source": source,
                "author": author,
                "character_id": None,
            },
        )

    async def send_context(
        self,
        key: str,
        content: str,
        description: str | None = None,
    ):
        """
        Send context update (not shown in chat, but AI knows about it).

        Args:
            key: A unique key for this context (e.g., "chessboard")
            content: The context content (e.g., FEN notation)
            description: Optional spoken summary to inform AI
        """
        self.logger.info(f"Sending context ({key}): {content[:50]}...")

        # Use Voxta's context update API
        await self.bridge.update_context(
            context_key=key,
            contexts=[{"text": content}],
        )

        # If there's a description, send it as a low-priority message
        if description:
            await self.bridge.send_message(
                text=f"[CONTEXT UPDATE - {key}] {description}",
                do_reply=False,
                do_user_inference=False,
                do_character_inference=False,
            )

    async def tts_playback_start(
        self,
        character_id: str,
        message_id: str | None = None,
    ):
        """
        Signal that external TTS playback started (bridge playing audio).

        Args:
            character_id: The character speaking
            message_id: The message being spoken
        """
        self.logger.info(f"TTS playback started: {character_id}")

        # Update state
        old_state = self.state.ai_state
        self.state.ai_state = AIState.SPEAKING
        self.state.current_speaker_id = character_id

        # Tell Voxta so it knows speech is happening
        await self.bridge.speech_playback_start(message_id)

        # Broadcast state change if needed
        if old_state != AIState.SPEAKING:
            await self.event_emitter.emit(
                "ai_state_changed",
                {"old_state": old_state.value, "new_state": AIState.SPEAKING.value},
            )

    async def tts_playback_complete(
        self,
        character_id: str,
        message_id: str | None = None,
    ):
        """
        Signal that external TTS playback finished.

        Args:
            character_id: The character that was speaking
            message_id: The message that was spoken
        """
        self.logger.info(f"TTS playback complete: {character_id}")

        # Update state (only if not interrupted by external speaker)
        if not self.state.external_speaker_active:
            old_state = self.state.ai_state
            self.state.ai_state = AIState.IDLE
            self.state.current_speaker_id = None

            # Tell Voxta
            await self.bridge.speech_playback_complete(message_id)

            # Broadcast state change if needed
            if old_state != AIState.IDLE:
                await self.event_emitter.emit(
                    "ai_state_changed",
                    {"old_state": old_state.value, "new_state": AIState.IDLE.value},
                )

    # ─────────────────────────────────────────────────────────────
    # Debug / Inspection
    # ─────────────────────────────────────────────────────────────

    def get_voxta_history(self) -> list[dict]:
        """Get raw Voxta event history."""
        return list(self.bridge.event_history)

    def get_connected_clients(self) -> dict[str, Any]:
        """Get information about all clients (connected or with history)."""
        all_client_ids = set(self.ws_manager.clients.keys()) | set(self.ws_manager.histories.keys())
        result = {}
        for client_id in all_client_ids:
            client = self.ws_manager.clients.get(client_id)
            history = self.ws_manager.histories.get(client_id, [])
            if client:
                info = client.to_debug_dict(history_len=len(history))
                info["connected"] = True
            else:
                info = {
                    "client_id": client_id,
                    "connected": False,
                    "message_count": len(history),
                    "subscribed_events": [],
                }
            result[client_id] = info
        return result

    def get_client_history(self, client_id: str) -> list[dict]:
        """Get message history for a specific client."""
        return self.ws_manager.get_client_history(client_id)
