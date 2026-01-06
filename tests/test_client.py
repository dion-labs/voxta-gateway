"""Tests for the GatewayClient module."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

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

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Test client start and stop sequence."""
        client = GatewayClient(gateway_url="http://localhost:8081")

        with patch("httpx.AsyncClient") as mock_http_cls, patch(
            "websockets.connect", new_callable=AsyncMock
        ) as mock_ws_connect:
            mock_http = mock_http_cls.return_value
            mock_http.aclose = AsyncMock()

            mock_ws = AsyncMock()
            mock_ws_connect.return_value = mock_ws

            # Mock the snapshot response
            mock_ws.recv.return_value = json.dumps(
                {
                    "type": "snapshot",
                    "state": {
                        "connected": True,
                        "chat_active": False,
                        "ai_state": "idle",
                        "characters": [],
                    },
                }
            )

            # Make _listen stay open until we stop it
            listen_event = asyncio.Event()

            async def mock_aiter(_):
                await listen_event.wait()
                yield json.dumps({"type": "test"})

            mock_ws.__aiter__ = mock_aiter

            # We want to run start, but it has a while self._running loop.
            # We can use a task and then stop it.
            client_task = asyncio.create_task(client.start())

            # Wait for it to connect
            for _ in range(10):
                if client.connection_state == ConnectionState.CONNECTED:
                    break
                await asyncio.sleep(0.05)

            assert client._running is True
            assert client.connection_state == ConnectionState.CONNECTED

            # Trigger disconnect and stop
            listen_event.set()
            await client.stop()
            assert client._running is False
            mock_ws.close.assert_called()
            await client_task

    @pytest.mark.asyncio
    async def test_connect_once_success(self):
        """Test successful one-time connection."""
        client = GatewayClient()
        with patch("httpx.AsyncClient") as mock_http_cls, patch(
            "websockets.connect", new_callable=AsyncMock
        ) as mock_ws_connect:
            mock_http = mock_http_cls.return_value
            mock_http.aclose = AsyncMock()

            mock_ws = AsyncMock()
            mock_ws_connect.return_value = mock_ws
            mock_ws.recv.return_value = json.dumps(
                {"type": "snapshot", "state": {"connected": True, "chat_active": True}}
            )

            result = await client.connect_once()
            assert result is True
            assert client.connection_state == ConnectionState.READY

    @pytest.mark.asyncio
    async def test_http_actions(self):
        """Test HTTP action methods (send_dialogue, health_check, etc)."""
        client = GatewayClient()
        client.state.chat_active = True

        with patch("httpx.AsyncClient") as mock_http_cls:
            mock_http = mock_http_cls.return_value
            mock_http.post = AsyncMock()
            mock_http.get = AsyncMock()

            # health_check
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"status": "ok"}
            mock_resp.status_code = 200
            mock_http.get.return_value = mock_resp

            res = await client.health_check()
            assert res["status"] == "ok"

            # send_dialogue
            mock_post_resp = MagicMock()
            mock_post_resp.status_code = 200
            mock_http.post.return_value = mock_post_resp

            res = await client.send_dialogue("hello")
            assert res is True

            # external_speaker_start
            res = await client.external_speaker_start("game", "reason")
            assert res is True

    @pytest.mark.asyncio
    async def test_wait_for_chat(self):
        """Test wait_for_chat utility."""
        client = GatewayClient()
        client.state.chat_active = False

        wait_task = asyncio.create_task(client.wait_for_chat(timeout=1.0))
        await asyncio.sleep(0.1)

        # Simulate chat started event
        await client._handle_event({"type": "chat_started", "data": {"characters": []}})

        result = await wait_task
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_idle(self):
        """Test wait_for_idle utility."""
        client = GatewayClient()
        client.state.ai_state = "speaking"

        wait_task = asyncio.create_task(client.wait_for_idle(timeout=1.0))
        await asyncio.sleep(0.1)

        # Simulate state changed event
        await client._handle_event({"type": "ai_state_changed", "data": {"new_state": "idle"}})

        result = await wait_task
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_chat_timeout(self):
        """Test wait_for_chat timeout."""
        client = GatewayClient()
        client.state.chat_active = False

        result = await client.wait_for_chat(timeout=0.01)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_state_and_health(self):
        """Test get_state and health_check."""
        client = GatewayClient()
        with patch("httpx.AsyncClient") as mock_http_cls:
            mock_http = mock_http_cls.return_value
            mock_http.get = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"val": 1}
            mock_resp.status_code = 200
            mock_http.get.return_value = mock_resp

            assert await client.get_state() == {"val": 1}
            assert await client.health_check() == {"val": 1}

    @pytest.mark.asyncio
    async def test_tts_playback_actions(self):
        """Test TTS playback start/complete."""
        client = GatewayClient()
        with patch("httpx.AsyncClient") as mock_http_cls:
            mock_http = mock_http_cls.return_value
            mock_http.post = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_http.post.return_value = mock_resp

            assert await client.tts_playback_start("c1", "m1") is True
            assert await client.tts_playback_complete("c1", "m1") is True

    @pytest.mark.asyncio
    async def test_handler_error_isolation(self):
        """Test that one failing handler doesn't stop others."""
        client = GatewayClient()

        results = []

        @client.on("test")
        async def failing_handler(_):
            raise RuntimeError("Boom")

        @client.on("test")
        async def success_handler(data):
            results.append(data)

        await client._emit("test", {"ok": True})
        assert results == [{"ok": True}]

    @pytest.mark.asyncio
    async def test_start_connection_error(self):
        """Test reconnection logic on error."""
        client = GatewayClient(reconnect_delay=0.01)
        client._running = True

        with patch("websockets.connect", new_callable=AsyncMock) as mock_ws_connect:
            mock_ws_connect.side_effect = [Exception("Fail"), AsyncMock()]

            # This is hard to test without an infinite loop,
            # so we'll just test one iteration of _connect failure
            import contextlib

            with contextlib.suppress(Exception):
                await asyncio.wait_for(client._connect(), timeout=0.1)

            assert client.connection_state == ConnectionState.CONNECTING

    @pytest.mark.asyncio
    async def test_connect_with_filters(self):
        """Test connection with source filters."""
        client = GatewayClient(filters={"dialogue": ["user"]})
        with patch("websockets.connect", new_callable=AsyncMock) as mock_ws_connect:
            mock_ws = AsyncMock()
            mock_ws_connect.return_value = mock_ws
            mock_ws.recv.return_value = json.dumps(
                {"type": "snapshot", "state": {"connected": True}}
            )

            await client._connect()
            # Verify filters were sent in subscription
            sent_args = json.loads(mock_ws.send.call_args[0][0])
            assert sent_args["filters"] == {"dialogue": ["user"]}
