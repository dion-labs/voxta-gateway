"""
WebSocket Manager - Client registry with selective event broadcasting.

This module manages WebSocket connections from downstream applications,
tracking their event subscriptions and routing events only to clients
that have subscribed to receive them.
"""

import contextlib
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket


@dataclass
class ConnectedClient:
    """Represents a connected WebSocket client."""

    client_id: str
    websocket: WebSocket
    subscribed_events: set[str] = field(default_factory=set)
    # event_type -> set of allowed sources. If empty or missing, all sources allowed.
    source_filters: dict[str, set[str]] = field(default_factory=dict)
    connected_at: float = field(default_factory=time.time)
    last_message_at: float = field(default_factory=time.time)

    def to_debug_dict(self, history_len: int = 0) -> dict:
        """Convert to dictionary for debug endpoints."""
        return {
            "client_id": self.client_id,
            "subscribed_events": list(self.subscribed_events),
            "source_filters": {k: list(v) for k, v in self.source_filters.items()},
            "message_count": history_len,
            "connected_at": self.connected_at,
            "last_message_at": self.last_message_at,
        }


class WebSocketManager:
    """
    Manages WebSocket connections and event routing.

    Features:
    - Client registration with event subscriptions
    - Selective broadcasting based on subscriptions
    - Per-client message history for debugging (persists across reconnects)
    - Automatic cleanup on disconnect

    Usage:
        manager = WebSocketManager()

        # In WebSocket endpoint:
        await manager.connect(websocket, "my-client", ["ai_state_changed"])
        # ... later ...
        await manager.broadcast("ai_state_changed", {"new_state": "speaking"})
    """

    # Special subscription that receives all events
    ALL_EVENTS = "all"

    def __init__(self, logger: logging.Logger | None = None):
        self.clients: dict[str, ConnectedClient] = {}
        self.histories: dict[str, deque[dict]] = {}
        self.logger = logger or logging.getLogger("WebSocketManager")

    async def connect(
        self,
        websocket: WebSocket,
        client_id: str,
        events: list[str] | None = None,
        source_filters: dict[str, list[str]] | None = None,
    ) -> ConnectedClient:
        """
        Register a new WebSocket client.

        Args:
            websocket: The WebSocket connection
            client_id: Unique identifier for this client
            events: List of event types to subscribe to
            source_filters: Optional dictionary mapping event types to allowed sources

        Returns:
            The created ConnectedClient instance
        """
        # Handle duplicate client IDs by disconnecting old connection
        if client_id in self.clients:
            self.logger.warning(f"Client {client_id} reconnecting, closing old connection")
            await self.disconnect(client_id)

        client = ConnectedClient(
            client_id=client_id,
            websocket=websocket,
            subscribed_events=set(events) if events else {self.ALL_EVENTS},
            source_filters={k: set(v) for k, v in source_filters.items()} if source_filters else {},
        )

        self.clients[client_id] = client

        # Initialize or preserve history
        if client_id not in self.histories:
            self.histories[client_id] = deque(maxlen=100)

        # Log connection event to history
        conn_event_data = {"client_id": client_id}
        conn_event = {
            "type": "client_connected",
            "data": conn_event_data,
            "timestamp": time.time(),
        }
        self.histories[client_id].append(conn_event)

        # Broadcast connection event
        await self.broadcast("client_connected", conn_event_data)

        self.logger.info(
            f"Client connected: {client_id} (subscribed to: {client.subscribed_events}, "
            f"filters: {client.source_filters})"
        )

        return client

    async def disconnect(self, client_id: str):
        """
        Disconnect and remove a client.

        Args:
            client_id: The client to disconnect
        """
        if client_id in self.clients:
            client = self.clients[client_id]
            with contextlib.suppress(Exception):
                await client.websocket.close()

            # Remove from registry FIRST to avoid recursion if broadcast fails
            del self.clients[client_id]

            # Log and broadcast disconnect event
            await self._log_disconnect(client_id)
            self.logger.info(f"Client disconnected: {client_id}")

    async def remove(self, client_id: str):
        """
        Remove a client without closing (use when already disconnected).

        Args:
            client_id: The client to remove
        """
        if client_id in self.clients:
            # Remove from registry FIRST to avoid recursion if broadcast fails
            del self.clients[client_id]

            # Log and broadcast disconnect event
            await self._log_disconnect(client_id)
            self.logger.info(f"Client removed: {client_id}")

    async def _log_disconnect(self, client_id: str):
        """Log a disconnect event to history."""
        if client_id in self.histories:
            disc_event_data = {"client_id": client_id}
            disc_event = {
                "type": "client_disconnected",
                "data": disc_event_data,
                "timestamp": time.time(),
            }
            self.histories[client_id].append(disc_event)
            await self.broadcast("client_disconnected", disc_event_data)

    def clear_history(self, client_id: str):
        """
        Clear message history for a client.

        Args:
            client_id: The client to clear history for
        """
        if client_id in self.histories:
            self.histories[client_id].clear()
            self.logger.info(f"Cleared history for client: {client_id}")

    async def broadcast(self, event_type: str, data: dict[str, Any]):
        """
        Broadcast an event to all subscribed clients.

        Args:
            event_type: The type of event
            data: The event data payload
        """
        message = {
            "type": event_type,
            "data": data,
            "timestamp": time.time(),
        }

        disconnected: list[str] = []
        source = data.get("source")

        for client_id, client in self.clients.items():
            # 1. Check if client is subscribed to this event
            is_subscribed = (
                self.ALL_EVENTS in client.subscribed_events
                or event_type in client.subscribed_events
            )
            if not is_subscribed:
                continue

            # 2. Check source filters if applicable
            if source and event_type in client.source_filters:
                allowed_sources = client.source_filters[event_type]
                if allowed_sources and source not in allowed_sources:
                    continue

            try:
                await client.websocket.send_json(message)
                # Add to history (which persists across reconnects)
                if client_id in self.histories:
                    self.histories[client_id].append(message)
                client.last_message_at = time.time()
            except Exception as e:
                self.logger.warning(f"Failed to send to {client_id}: {e}")
                disconnected.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected:
            await self.remove(client_id)

    async def send_to_client(self, client_id: str, event_type: str, data: dict[str, Any]):
        """
        Send an event to a specific client.

        Args:
            client_id: The target client
            event_type: The type of event
            data: The event data payload
        """
        if client_id not in self.clients:
            return

        client = self.clients[client_id]
        message = {
            "type": event_type,
            "data": data,
            "timestamp": time.time(),
        }

        try:
            await client.websocket.send_json(message)
            # Add to history
            if client_id in self.histories:
                self.histories[client_id].append(message)
            client.last_message_at = time.time()
        except Exception as e:
            self.logger.warning(f"Failed to send to {client_id}: {e}")
            await self.remove(client_id)

    def update_subscriptions(
        self,
        client_id: str,
        events: list[str],
        source_filters: dict[str, list[str]] | None = None,
    ):
        """
        Update a client's event subscriptions.

        Args:
            client_id: The client to update
            events: New list of events to subscribe to
            source_filters: Optional dictionary mapping event types to allowed sources
        """
        if client_id in self.clients:
            self.clients[client_id].subscribed_events = set(events)
            if source_filters is not None:
                self.clients[client_id].source_filters = {
                    k: set(v) for k, v in source_filters.items()
                }
            self.logger.info(
                f"Updated subscriptions for {client_id}: {events} (filters: {source_filters})"
            )

    def get_client(self, client_id: str) -> ConnectedClient | None:
        """Get a client by ID."""
        return self.clients.get(client_id)

    def get_all_clients(self) -> dict[str, ConnectedClient]:
        """Get all connected clients."""
        return self.clients.copy()

    def get_client_history(self, client_id: str) -> list[dict]:
        """
        Get message history for a client.

        Args:
            client_id: The client to get history for

        Returns:
            List of messages sent to this client
        """
        if client_id in self.histories:
            return list(self.histories[client_id])
        return []

    def get_subscriber_count(self, event_type: str) -> int:
        """
        Get the number of clients subscribed to an event type.

        Args:
            event_type: The event type to check

        Returns:
            Number of subscribed clients
        """
        count = 0
        for client in self.clients.values():
            if (
                self.ALL_EVENTS in client.subscribed_events
                or event_type in client.subscribed_events
            ):
                count += 1
        return count

    @property
    def client_count(self) -> int:
        """Get the total number of connected clients."""
        return len(self.clients)
