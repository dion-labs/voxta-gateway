"""
Internal event bus for the Gateway.

This emitter allows different components of the gateway to communicate
without tight coupling. Events emitted here are internal to the gateway
and may be transformed before being sent to WebSocket clients.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

# Type alias for event callbacks
EventCallback = Callable[[dict[str, Any]], Awaitable[None]]


class EventEmitter:
    """
    Simple async event emitter for internal gateway communication.

    Usage:
        emitter = EventEmitter()

        @emitter.on("event_name")
        async def handler(data):
            print(f"Received: {data}")

        await emitter.emit("event_name", {"key": "value"})
    """

    def __init__(self, logger: logging.Logger | None = None):
        self._listeners: dict[str, list[EventCallback]] = {}
        self.logger = logger or logging.getLogger("EventEmitter")

    def on(self, event_name: str, callback: EventCallback | None = None):
        """
        Register a callback for an event. Can be used as a decorator.

        Args:
            event_name: The event to listen for
            callback: The async callback function

        Returns:
            The callback (for decorator usage)
        """
        if callback is not None:
            if event_name not in self._listeners:
                self._listeners[event_name] = []
            self._listeners[event_name].append(callback)
            return callback

        # Decorator usage
        def decorator(func: EventCallback) -> EventCallback:
            if event_name not in self._listeners:
                self._listeners[event_name] = []
            self._listeners[event_name].append(func)
            return func

        return decorator

    def off(self, event_name: str, callback: EventCallback):
        """
        Remove a callback from an event.

        Args:
            event_name: The event to unsubscribe from
            callback: The callback to remove
        """
        if event_name in self._listeners:
            with contextlib.suppress(ValueError):
                self._listeners[event_name].remove(callback)

    async def emit(self, event_name: str, data: dict[str, Any] | None = None):
        """
        Emit an event to all registered listeners.

        Args:
            event_name: The event to emit
            data: The event data payload
        """
        if event_name not in self._listeners:
            return

        data = data or {}

        for callback in self._listeners[event_name]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                self.logger.error(f"Error in event handler for '{event_name}': {e}")

    def listener_count(self, event_name: str) -> int:
        """Get the number of listeners for an event."""
        return len(self._listeners.get(event_name, []))

    def clear(self, event_name: str | None = None):
        """
        Clear all listeners, or listeners for a specific event.

        Args:
            event_name: If provided, only clear listeners for this event
        """
        if event_name is None:
            self._listeners.clear()
        elif event_name in self._listeners:
            del self._listeners[event_name]
