"""
WebSocket Manager - Client registry with selective event broadcasting.

This module manages WebSocket connections from downstream applications,
tracking their event subscriptions and routing events only to clients
that have subscribed to receive them.
"""

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
    message_history: deque[dict] = field(default_factory=lambda: deque(maxlen=100))
    connected_at: float = field(default_factory=time.time)
    last_message_at: float = field(default_factory=time.time)

    def to_debug_dict(self) -> dict:
        """Convert to dictionary for debug endpoints."""
        return {
            "client_id": self.client_id,
            "subscribed_events": list(self.subscribed_events),
            "message_count": len(self.message_history),
            "connected_at": self.connected_at,
            "last_message_at": self.last_message_at,
        }


class WebSocketManager:
    """
    Manages WebSocket connections and event routing.

    Features:
    - Client registration with event subscriptions
    - Selective broadcasting based on subscriptions
    - Per-client message history for debugging
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
        self.logger = logger or logging.getLogger("WebSocketManager")

    async def connect(
        self,
        websocket: WebSocket,
        client_id: str,
        events: list[str] | None = None,
    ) -> ConnectedClient:
        """
        Register a new WebSocket client.

        Args:
            websocket: The WebSocket connection
            client_id: Unique identifier for this client
            events: List of event types to subscribe to

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
        )

        self.clients[client_id] = client
        self.logger.info(
            f"Client connected: {client_id} (subscribed to: {client.subscribed_events})"
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
            try:
                await client.websocket.close()
            except Exception:
                pass  # Already closed
            del self.clients[client_id]
            self.logger.info(f"Client disconnected: {client_id}")

    def remove(self, client_id: str):
        """
        Remove a client without closing (use when already disconnected).

        Args:
            client_id: The client to remove
        """
        if client_id in self.clients:
            del self.clients[client_id]
            self.logger.info(f"Client removed: {client_id}")

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

        for client_id, client in self.clients.items():
            # Check if client is subscribed to this event
            if (
                self.ALL_EVENTS in client.subscribed_events
                or event_type in client.subscribed_events
            ):
                try:
                    await client.websocket.send_json(message)
                    client.message_history.append(message)
                    client.last_message_at = time.time()
                except Exception as e:
                    self.logger.warning(f"Failed to send to {client_id}: {e}")
                    disconnected.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected:
            self.remove(client_id)

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
            client.message_history.append(message)
            client.last_message_at = time.time()
        except Exception as e:
            self.logger.warning(f"Failed to send to {client_id}: {e}")
            self.remove(client_id)

    def update_subscriptions(self, client_id: str, events: list[str]):
        """
        Update a client's event subscriptions.

        Args:
            client_id: The client to update
            events: New list of events to subscribe to
        """
        if client_id in self.clients:
            self.clients[client_id].subscribed_events = set(events)
            self.logger.info(f"Updated subscriptions for {client_id}: {events}")

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
        if client_id in self.clients:
            return list(self.clients[client_id].message_history)
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
            if self.ALL_EVENTS in client.subscribed_events or event_type in client.subscribed_events:
                count += 1
        return count

    @property
    def client_count(self) -> int:
        """Get the total number of connected clients."""
        return len(self.clients)

