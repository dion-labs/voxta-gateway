from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from voxta_gateway.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.asyncio
async def test_health_endpoint():
    with patch("voxta_gateway.main.gateway") as mock_gateway:
        mock_gateway.state.connected = True
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "voxta_connected": True}


@pytest.mark.asyncio
async def test_state_endpoint():
    with patch("voxta_gateway.main.gateway") as mock_gateway:
        mock_gateway.state.to_snapshot.return_value = {
            "connected": True,
            "chat_active": True,
            "ai_state": "idle",
            "external_speaker_active": False,
            "external_speaker_source": None,
            "characters": [],
        }
        client = TestClient(app)
        response = client.get("/state")
        assert response.status_code == 200
        assert response.json()["connected"] is True


@pytest.mark.asyncio
async def test_dialogue_endpoint():
    with patch("voxta_gateway.main.gateway") as mock_gateway:
        mock_gateway.send_dialogue = AsyncMock()
        client = TestClient(app)
        response = client.post("/dialogue", json={"text": "Hello", "source": "user"})
        assert response.status_code == 200
        mock_gateway.send_dialogue.assert_called_with(
            text="Hello", source="user", author=None, immediate_reply=None
        )


@pytest.mark.asyncio
async def test_context_endpoint():
    with patch("voxta_gateway.main.gateway") as mock_gateway:
        mock_gateway.send_context = AsyncMock()
        client = TestClient(app)
        fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        response = client.post("/context", json={"key": "board", "content": fen})
        assert response.status_code == 200
        mock_gateway.send_context.assert_called_with(key="board", content=fen, description=None)


@pytest.mark.asyncio
async def test_external_speaker_endpoints():
    with patch("voxta_gateway.main.gateway") as mock_gateway:
        mock_gateway.external_speaker_start = AsyncMock()
        mock_gateway.external_speaker_stop = AsyncMock()
        client = TestClient(app)

        # Start
        response = client.post("/external_speaker_start", json={"source": "game", "reason": "test"})
        assert response.status_code == 200
        mock_gateway.external_speaker_start.assert_called_with(source="game", reason="test")

        # Stop
        response = client.post("/external_speaker_stop", json={"trigger_response": True})
        assert response.status_code == 200
        mock_gateway.external_speaker_stop.assert_called_with(trigger_response=True)


@pytest.mark.asyncio
async def test_debug_endpoints():
    with patch("voxta_gateway.main.gateway") as mock_gateway:
        mock_gateway.get_connected_clients.return_value = {"c1": {}}

        # Configure get_client_history to return based on arg
        def get_history_side_effect(cid):
            if cid == "c1":
                return [{"type": "msg"}]
            return []

        mock_gateway.get_client_history.side_effect = get_history_side_effect
        mock_gateway.ws_manager.histories = {"c1": []}
        mock_gateway.get_voxta_history.return_value = []

        client = TestClient(app)

        # Clients
        assert client.get("/debug/clients").status_code == 200

        # History
        assert client.get("/debug/clients/c1/history").status_code == 200
        assert client.get("/debug/clients/unknown/history").status_code == 404

        # Clear
        assert client.post("/debug/clients/c1/clear").status_code == 200

        # Voxta history
        assert client.get("/debug/voxta/history").status_code == 200


@pytest.mark.asyncio
async def test_tts_playback_endpoints():
    with patch("voxta_gateway.main.gateway") as mock_gateway:
        mock_gateway.tts_playback_start = AsyncMock()
        mock_gateway.tts_playback_complete = AsyncMock()
        client = TestClient(app)

        # Start
        response = client.post(
            "/tts_playback_start", json={"character_id": "c1", "message_id": "m1"}
        )
        assert response.status_code == 200
        mock_gateway.tts_playback_start.assert_called_with(character_id="c1", message_id="m1")

        # Complete
        response = client.post(
            "/tts_playback_complete", json={"character_id": "c1", "message_id": "m1"}
        )
        assert response.status_code == 200
        mock_gateway.tts_playback_complete.assert_called_with(character_id="c1", message_id="m1")


@pytest.mark.asyncio
async def test_gateway_not_initialized():
    with patch("voxta_gateway.main.gateway", None):
        client = TestClient(app)
        assert client.get("/health").status_code == 503
        assert client.get("/state").status_code == 503
        assert client.post("/dialogue", json={"text": "hi"}).status_code == 503


@pytest.mark.asyncio
async def test_websocket_flow():
    with patch("voxta_gateway.main.gateway") as mock_gateway:
        mock_gateway.state.to_snapshot.return_value = {"connected": True}
        mock_gateway.ws_manager.connect = AsyncMock()
        mock_gateway.ws_manager.remove = AsyncMock()

        client = TestClient(app)
        with client.websocket_connect("/ws") as websocket:
            # 1. Send subscribe
            websocket.send_json({"type": "subscribe", "client_id": "c1", "events": ["all"]})

            # 2. Receive snapshot
            data = websocket.receive_json()
            assert data["type"] == "snapshot"

            # 3. Send ping
            websocket.send_json({"type": "ping"})
            data = websocket.receive_json()
            assert data["type"] == "pong"

            # 4. Send subscription update
            websocket.send_json({"type": "subscribe", "events": ["dialogue"]})
            # No response expected but it should call update_subscriptions

        mock_gateway.ws_manager.remove.assert_called_with("c1")


@pytest.mark.asyncio
async def test_websocket_timeout():
    client = TestClient(app)
    # This might be hard to test timeout without actually waiting 10s
    # but we can try a fast disconnect
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws"):
        pass


@pytest.mark.asyncio
async def test_index_endpoint():
    client = TestClient(app)
    # If static/index.html doesn't exist it returns JSON
    response = client.get("/")
    assert response.status_code == 200
