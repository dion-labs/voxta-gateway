"""Tests for the GatewayClient module."""

import pytest

from voxta_gateway.client import ConnectionState, GatewayClient, GatewayState


class TestGatewayState:
    """Tests for the GatewayState dataclass."""

    def test_default_state(self):
        """Test default state values."""
        state = GatewayState()
        assert state.connected is False
        assert state.chat_active is False
        assert state.ai_state == "idle"
        assert state.characters == []

    def test_update_from_snapshot(self):
        """Test updating state from a snapshot."""
        state = GatewayState()

        state.update_from_snapshot(
            {
                "connected": True,
                "chat_active": True,
                "ai_state": "speaking",
                "current_speaker_id": "char-123",
                "external_speaker_active": True,
                "external_speaker_source": "game",
                "characters": [{"id": "char-1", "name": "Apex"}],
            }
        )

        assert state.connected is True
        assert state.chat_active is True
        assert state.ai_state == "speaking"
        assert state.current_speaker_id == "char-123"
        assert state.external_speaker_active is True
        assert state.external_speaker_source == "game"
        assert len(state.characters) == 1
        assert state.characters[0]["name"] == "Apex"


class TestGatewayClient:
    """Tests for the GatewayClient class."""

    def test_initialization(self):
        """Test client initialization."""
        client = GatewayClient(
            gateway_url="http://localhost:8081",
            client_id="test-client",
            events=["dialogue_received"],
        )

        assert client.gateway_url == "http://localhost:8081"
        assert client.client_id == "test-client"
        assert client.events == ["dialogue_received"]
        assert client.connection_state == ConnectionState.DISCONNECTED

    def test_default_events(self):
        """Test default event subscription."""
        client = GatewayClient()

        assert "chat_started" in client.events
        assert "chat_closed" in client.events
        assert "ai_state_changed" in client.events

    def test_event_registration_decorator(self):
        """Test registering event handlers via decorator."""
        client = GatewayClient()

        @client.on("test_event")
        async def handler(_):
            pass

        assert "test_event" in client._handlers
        assert handler in client._handlers["test_event"]

    def test_event_registration_method(self):
        """Test registering event handlers via method."""
        client = GatewayClient()

        async def handler(_):
            pass

        client.on("test_event", handler)

        assert "test_event" in client._handlers
        assert handler in client._handlers["test_event"]

    def test_event_unregistration(self):
        """Test removing event handlers."""
        client = GatewayClient()

        async def handler(_):
            pass

        client.on("test_event", handler)
        client.off("test_event", handler)

        assert handler not in client._handlers.get("test_event", [])

    def test_is_connected_property(self):
        """Test is_connected property."""
        client = GatewayClient()

        assert client.is_connected is False

        client.connection_state = ConnectionState.CONNECTED
        assert client.is_connected is True

        client.connection_state = ConnectionState.READY
        assert client.is_connected is True

        client.connection_state = ConnectionState.CONNECTING
        assert client.is_connected is False

    def test_is_ready_property(self):
        """Test is_ready property."""
        client = GatewayClient()

        assert client.is_ready is False

        client.connection_state = ConnectionState.CONNECTED
        assert client.is_ready is False

        client.connection_state = ConnectionState.READY
        assert client.is_ready is True

    def test_chat_active_property(self):
        """Test chat_active property."""
        client = GatewayClient()

        assert client.chat_active is False

        client.state.chat_active = True
        assert client.chat_active is True

    def test_ai_state_property(self):
        """Test ai_state property."""
        client = GatewayClient()

        assert client.ai_state == "idle"

        client.state.ai_state = "thinking"
        assert client.ai_state == "thinking"

    def test_characters_property(self):
        """Test characters property."""
        client = GatewayClient()

        assert client.characters == []

        client.state.characters = [{"id": "1", "name": "Test"}]
        assert len(client.characters) == 1

    @pytest.mark.asyncio
    async def test_emit_to_handlers(self):
        """Test event emission to handlers."""
        client = GatewayClient()
        received = []

        @client.on("test_event")
        async def handler(data):
            received.append(data)

        await client._emit("test_event", {"value": 42})

        assert len(received) == 1
        assert received[0]["value"] == 42

    @pytest.mark.asyncio
    async def test_emit_no_handlers(self):
        """Test emission when no handlers registered."""
        client = GatewayClient()

        # Should not raise
        await client._emit("nonexistent_event", {"value": 1})

    @pytest.mark.asyncio
    async def test_handle_chat_started_event(self):
        """Test handling chat_started event updates state."""
        client = GatewayClient()
        client.connection_state = ConnectionState.CONNECTED

        await client._handle_event(
            {"type": "chat_started", "data": {"characters": [{"id": "1", "name": "Apex"}]}}
        )

        assert client.state.chat_active is True
        assert client.connection_state == ConnectionState.READY
        assert len(client.state.characters) == 1

    @pytest.mark.asyncio
    async def test_handle_chat_closed_event(self):
        """Test handling chat_closed event updates state."""
        client = GatewayClient()
        client.state.chat_active = True
        client.state.characters = [{"id": "1", "name": "Test"}]
        client.connection_state = ConnectionState.READY

        await client._handle_event({"type": "chat_closed", "data": {}})

        assert client.state.chat_active is False
        assert client.state.characters == []
        assert client.connection_state == ConnectionState.CONNECTED

    @pytest.mark.asyncio
    async def test_handle_ai_state_changed_event(self):
        """Test handling ai_state_changed event updates state."""
        client = GatewayClient()

        await client._handle_event(
            {"type": "ai_state_changed", "data": {"old_state": "idle", "new_state": "thinking"}}
        )

        assert client.state.ai_state == "thinking"

    @pytest.mark.asyncio
    async def test_send_dialogue_requires_active_chat(self):
        """Test send_dialogue raises when no active chat."""
        client = GatewayClient()
        client.state.chat_active = False

        with pytest.raises(RuntimeError, match="no active chat"):
            await client.send_dialogue("Hello")

    @pytest.mark.asyncio
    async def test_send_context_requires_active_chat(self):
        """Test send_context raises when no active chat."""
        client = GatewayClient()
        client.state.chat_active = False

        with pytest.raises(RuntimeError, match="no active chat"):
            await client.send_context("key", "content")
