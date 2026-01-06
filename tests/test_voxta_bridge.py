import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voxta_gateway.event_emitter import EventEmitter
from voxta_gateway.state import AIState, GatewayState
from voxta_gateway.voxta_bridge import VoxtaBridge


@pytest.fixture
def state():
    return GatewayState()


@pytest.fixture
def event_emitter():
    return EventEmitter()


@pytest.fixture
def bridge(state, event_emitter):
    return VoxtaBridge(voxta_url="http://localhost:5384", state=state, event_emitter=event_emitter)


@pytest.mark.asyncio
async def test_bridge_start_stop(bridge):
    with patch("voxta_gateway.voxta_bridge.VoxtaClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.negotiate.return_value = ("token", {"cookie": "value"})
        mock_client.connect = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.running = True

        # We need to make _connect stop eventually
        bridge._running = True

        # Start in task so we can cancel it or let it run
        asyncio.create_task(bridge.start())
        await asyncio.sleep(0.1)

        assert bridge._running is True
        assert bridge.state.connected is True

        await bridge.stop()
        assert bridge._running is False
        assert bridge.client is None
        assert bridge.state.connected is False


@pytest.mark.asyncio
async def test_on_ready(bridge):
    await bridge._on_ready("session-123")
    assert bridge.state.session_id == "session-123"
    assert bridge.state.connected is True

    await bridge._on_ready({"sessionId": "session-456"})
    assert bridge.state.session_id == "session-456"


@pytest.mark.asyncio
async def test_on_chat_started(bridge):
    data = {
        "chatId": "chat-123",
        "sessionId": "session-123",
        "context": {
            "characters": [
                {
                    "id": "char-1",
                    "name": "Apex",
                    "creatorNotes": "Notes",
                    "textGenService": "Service",
                }
            ]
        },
    }

    received_events = []

    @bridge.event_emitter.on("chat_started")
    async def on_chat_started(payload):
        received_events.append(("chat_started", payload))

    await bridge._on_chat_started(data)

    assert bridge.state.chat_id == "chat-123"
    assert "char-1" in bridge.state.characters
    assert bridge.state.characters["char-1"].name == "Apex"
    assert len(received_events) == 1


@pytest.mark.asyncio
async def test_on_chat_closed(bridge):
    bridge.state.chat_id = "chat-123"
    bridge.state.characters["char-1"] = MagicMock()

    await bridge._on_chat_closed({"chatId": "chat-123"})

    assert bridge.state.chat_id is None
    assert len(bridge.state.characters) == 0


@pytest.mark.asyncio
async def test_on_reply_generating(bridge):
    received_events = []

    @bridge.event_emitter.on("ai_state_changed")
    async def on_state_changed(payload):
        received_events.append(payload)

    await bridge._on_reply_generating({})
    assert bridge.state.ai_state == AIState.THINKING
    assert len(received_events) == 1
    assert received_events[0]["new_state"] == AIState.THINKING.value


@pytest.mark.asyncio
async def test_on_reply_start(bridge):
    data = {"messageId": "msg-1", "senderId": "char-1"}
    await bridge._on_reply_start(data)
    assert bridge.state.last_message_id == "msg-1"
    assert bridge.state.current_speaker_id == "char-1"


@pytest.mark.asyncio
async def test_on_speech_playback_start_stop(bridge):
    await bridge._on_speech_playback_start({})
    assert bridge.state.ai_state == AIState.SPEAKING

    await bridge._on_speech_playback_complete({})
    assert bridge.state.ai_state == AIState.IDLE
    assert bridge.state.current_speaker_id is None


@pytest.mark.asyncio
async def test_low_level_ops(bridge):
    bridge.client = MagicMock()
    bridge.client.interrupt = AsyncMock()
    bridge.client.send_message = AsyncMock()
    bridge.client.speech_playback_start = AsyncMock()
    bridge.state.session_id = "sess-1"

    await bridge.interrupt()
    bridge.client.interrupt.assert_called_with("sess-1")

    await bridge.send_message("hello")
    bridge.client.send_message.assert_called()

    await bridge.speech_playback_start("msg-1")
    bridge.client.speech_playback_start.assert_called_with(session_id="sess-1", message_id="msg-1")


@pytest.mark.asyncio
async def test_on_participants_updated(bridge):
    data = {"participants": [{"characterId": "char-2", "name": "Bob"}]}
    await bridge._on_participants_updated(data)
    assert "char-2" in bridge.state.characters
    assert bridge.state.characters["char-2"].name == "Bob"


@pytest.mark.asyncio
async def test_on_reply_events(bridge):
    # Chunk
    chunk_data = {"messageId": "m1", "senderId": "c1", "text": "h", "startIndex": 0}
    await bridge._on_reply_chunk(chunk_data)
    # End
    await bridge._on_reply_end({"messageId": "m1"})
    # Cancelled
    await bridge._on_reply_cancelled({"messageId": "m1"})
    assert bridge.state.ai_state == AIState.IDLE


@pytest.mark.asyncio
async def test_on_message_events(bridge):
    # Full message
    msg_data = {"messageId": "m1", "text": "hello", "senderId": "c1", "role": "assistant"}
    await bridge._on_message(msg_data)
    assert bridge.state.last_message_text == "hello"

    # Update
    await bridge._on_message_update({"text": "hello updated"})
    assert bridge.state.last_message_text == "hello updated"


@pytest.mark.asyncio
async def test_on_interrupt_speech(bridge):
    bridge.state.ai_state = AIState.SPEAKING
    await bridge._on_interrupt_speech({})
    assert bridge.state.ai_state == AIState.IDLE


@pytest.mark.asyncio
async def test_on_action(bridge):
    data = {"value": "do_something", "arguments": [{"arg1": "val1"}], "senderId": "char-1"}
    received = []

    @bridge.event_emitter.on("app_trigger")
    async def on_trigger(payload):
        received.append(payload)

    await bridge._on_action(data)
    assert len(received) == 1
    assert received[0]["name"] == "do_something"
    assert received[0]["arguments"] == {"arg1": "val1"}


@pytest.mark.asyncio
async def test_record_event(bridge):
    await bridge._record_event({"$type": "test", "val": 1})
    assert len(bridge.event_history) == 1
    assert bridge.event_history[0]["type"] == "test"


@pytest.mark.asyncio
async def test_update_context(bridge):
    bridge.client = MagicMock()
    bridge.client.update_context = AsyncMock()
    bridge.state.session_id = "s1"

    await bridge.update_context(context_key="ck", contexts=[{"text": "ctx"}])
    bridge.client.update_context.assert_called()


@pytest.mark.asyncio
async def test_speech_playback_complete(bridge):
    bridge.client = MagicMock()
    bridge.client.speech_playback_complete = AsyncMock()
    bridge.state.session_id = "s1"

    await bridge.speech_playback_complete("m1")
    bridge.client.speech_playback_complete.assert_called()


@pytest.mark.asyncio
async def test_character_speech_request(bridge):
    bridge.client = MagicMock()
    bridge.client.character_speech_request = AsyncMock()
    bridge.state.session_id = "s1"

    await bridge.character_speech_request("c1", "text")
    bridge.client.character_speech_request.assert_called()
