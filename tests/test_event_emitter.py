"""Tests for the EventEmitter module."""

import pytest


class TestEventEmitter:
    """Tests for the EventEmitter class."""

    @pytest.mark.asyncio
    async def test_basic_emit(self, event_emitter):
        """Test basic event emission."""
        received = []

        async def handler(data):
            received.append(data)

        event_emitter.on("test_event", handler)
        await event_emitter.emit("test_event", {"value": 42})

        assert len(received) == 1
        assert received[0]["value"] == 42

    @pytest.mark.asyncio
    async def test_multiple_handlers(self, event_emitter):
        """Test multiple handlers for same event."""
        received = []

        async def handler1(data):
            received.append(("h1", data))

        async def handler2(data):
            received.append(("h2", data))

        event_emitter.on("test_event", handler1)
        event_emitter.on("test_event", handler2)
        await event_emitter.emit("test_event", {"value": 1})

        assert len(received) == 2
        handlers = [r[0] for r in received]
        assert "h1" in handlers
        assert "h2" in handlers

    @pytest.mark.asyncio
    async def test_decorator_registration(self, event_emitter):
        """Test registering handler via decorator."""
        received = []

        @event_emitter.on("test_event")
        async def handler(data):
            received.append(data)

        await event_emitter.emit("test_event", {"value": 99})

        assert len(received) == 1
        assert received[0]["value"] == 99

    @pytest.mark.asyncio
    async def test_emit_no_handlers(self, event_emitter):
        """Test emitting to event with no handlers (should not error)."""
        await event_emitter.emit("nonexistent_event", {"value": 1})
        # Should complete without error

    @pytest.mark.asyncio
    async def test_off_removes_handler(self, event_emitter):
        """Test removing a handler."""
        received = []

        async def handler(data):
            received.append(data)

        event_emitter.on("test_event", handler)
        event_emitter.off("test_event", handler)
        await event_emitter.emit("test_event", {"value": 1})

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_off_nonexistent_handler(self, event_emitter):
        """Test removing a handler that doesn't exist (should not error)."""

        async def handler(_):
            pass

        # Should not error
        event_emitter.off("nonexistent_event", handler)
        event_emitter.off("test_event", handler)

    def test_listener_count(self, event_emitter):
        """Test counting listeners."""

        async def handler(_):
            pass

        assert event_emitter.listener_count("test_event") == 0

        event_emitter.on("test_event", handler)
        assert event_emitter.listener_count("test_event") == 1

        event_emitter.on("test_event", handler)  # Can add same handler twice
        assert event_emitter.listener_count("test_event") == 2

    def test_clear_specific_event(self, event_emitter):
        """Test clearing handlers for a specific event."""

        async def handler(_):
            pass

        event_emitter.on("event1", handler)
        event_emitter.on("event2", handler)

        event_emitter.clear("event1")

        assert event_emitter.listener_count("event1") == 0
        assert event_emitter.listener_count("event2") == 1

    def test_clear_all_events(self, event_emitter):
        """Test clearing all handlers."""

        async def handler(_):
            pass

        event_emitter.on("event1", handler)
        event_emitter.on("event2", handler)

        event_emitter.clear()

        assert event_emitter.listener_count("event1") == 0
        assert event_emitter.listener_count("event2") == 0

    @pytest.mark.asyncio
    async def test_handler_error_isolation(self, event_emitter):
        """Test that one handler's error doesn't affect others."""
        received = []

        async def error_handler(_):
            raise ValueError("Test error")

        async def good_handler(data):
            received.append(data)

        event_emitter.on("test_event", error_handler)
        event_emitter.on("test_event", good_handler)

        # Should not raise, and good_handler should still run
        await event_emitter.emit("test_event", {"value": 1})

        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_emit_with_none_data(self, event_emitter):
        """Test emitting with no data."""
        received = []

        async def handler(data):
            received.append(data)

        event_emitter.on("test_event", handler)
        await event_emitter.emit("test_event")

        assert len(received) == 1
        assert received[0] == {}
