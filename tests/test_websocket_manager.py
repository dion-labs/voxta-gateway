from unittest.mock import AsyncMock, MagicMock

import pytest

from voxta_gateway.websocket_manager import WebSocketManager


@pytest.fixture
def manager():
    return WebSocketManager()


@pytest.fixture
def mock_websocket():
    ws = MagicMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_connect_disconnect(manager, mock_websocket):
    client_id = "test-client"
    await manager.connect(mock_websocket, client_id, events=["test_event"])

    assert manager.client_count == 1
    assert client_id in manager.clients
    assert manager.get_subscriber_count("test_event") == 1

    await manager.disconnect(client_id)
    assert manager.client_count == 0
    mock_websocket.close.assert_called()


@pytest.mark.asyncio
async def test_broadcast(manager, mock_websocket):
    await manager.connect(mock_websocket, "client-1", events=["event-a"])

    # Broadcast matching event
    await manager.broadcast("event-a", {"data": 1})
    mock_websocket.send_json.assert_called()

    # Broadcast non-matching event
    mock_websocket.send_json.reset_mock()
    await manager.broadcast("event-b", {"data": 2})
    mock_websocket.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_broadcast_all(manager, mock_websocket):
    await manager.connect(mock_websocket, "client-1", events=["all"])
    await manager.broadcast("any-event", {"data": 1})
    mock_websocket.send_json.assert_called()


@pytest.mark.asyncio
async def test_source_filters(manager, mock_websocket):
    await manager.connect(
        mock_websocket, "client-1", events=["dialogue"], source_filters={"dialogue": ["user"]}
    )

    # Allowed source
    await manager.broadcast("dialogue", {"source": "user", "text": "hi"})
    mock_websocket.send_json.assert_called()

    # Filtered source
    mock_websocket.send_json.reset_mock()
    await manager.broadcast("dialogue", {"source": "game", "text": "npc hi"})
    mock_websocket.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_client_reconnect(manager, mock_websocket):
    client_id = "test-client"
    await manager.connect(mock_websocket, client_id)

    new_mock_ws = MagicMock()
    new_mock_ws.send_json = AsyncMock()
    new_mock_ws.close = AsyncMock()

    await manager.connect(new_mock_ws, client_id)

    assert manager.client_count == 1
    mock_websocket.close.assert_called()
    assert manager.clients[client_id].websocket == new_mock_ws


@pytest.mark.asyncio
async def test_broadcast_failure_cleanup(manager, mock_websocket):
    mock_websocket.send_json.side_effect = Exception("Connection lost")
    await manager.connect(mock_websocket, "client-1", events=["all"])

    await manager.broadcast("some-event", {})
    assert manager.client_count == 0


def test_to_debug_dict(manager, mock_websocket):
    client_id = "test-client"
    # Using a sync wrapper or just calling since we don't need to await for setup if we mock
    manager.histories[client_id] = [1, 2, 3]
    from voxta_gateway.websocket_manager import ConnectedClient

    client = ConnectedClient(client_id=client_id, websocket=mock_websocket)
    debug_dict = client.to_debug_dict(history_len=3)
    assert debug_dict["client_id"] == client_id
    assert debug_dict["message_count"] == 3


@pytest.mark.asyncio
async def test_send_to_client(manager, mock_websocket):
    client_id = "client-1"
    await manager.connect(mock_websocket, client_id)

    await manager.send_to_client(client_id, "direct", {"msg": "hi"})
    mock_websocket.send_json.assert_called()

    # Non-existent client
    mock_websocket.send_json.reset_mock()
    await manager.send_to_client("no-one", "direct", {"msg": "hi"})
    mock_websocket.send_json.assert_not_called()


def test_get_methods(manager):
    manager.clients["c1"] = MagicMock()
    assert manager.get_client("c1") is not None
    assert manager.get_client("c2") is None
    assert len(manager.get_all_clients()) == 1
