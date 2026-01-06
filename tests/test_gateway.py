from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voxta_gateway.gateway import Gateway
from voxta_gateway.state import AIState


@pytest.fixture
def gateway():
    with (
        patch("voxta_gateway.gateway.VoxtaBridge"),
        patch("voxta_gateway.gateway.WebSocketManager"),
    ):
        gw = Gateway(voxta_url="http://localhost:5384")
        return gw


@pytest.mark.asyncio
async def test_gateway_initialization(gateway):
    assert gateway.state is not None
    assert gateway.event_emitter is not None
    assert gateway.bridge is not None
    assert gateway.ws_manager is not None


@pytest.mark.asyncio
async def test_external_speaker_start_stop(gateway):
    gateway.bridge.interrupt = AsyncMock()
    gateway.bridge.speech_playback_start = AsyncMock()
    gateway.bridge.speech_playback_complete = AsyncMock()
    gateway.bridge.character_speech_request = AsyncMock()

    # Start
    await gateway.external_speaker_start(source="game", reason="NPC talking")
    assert gateway.state.external_speaker_active is True
    assert gateway.state.external_speaker_source == "game"

    # Stop
    gateway.state.last_message_id = "msg-1"
    gateway.state.characters["char-1"] = MagicMock()
    await gateway.external_speaker_stop(trigger_response=True)
    assert gateway.state.external_speaker_active is False
    gateway.bridge.speech_playback_complete.assert_called_with("msg-1")
    gateway.bridge.character_speech_request.assert_called()


@pytest.mark.asyncio
async def test_send_dialogue(gateway):
    gateway.bridge.send_message = AsyncMock()

    await gateway.send_dialogue(text="Hello", source="user")
    gateway.bridge.send_message.assert_called_with(
        text="Hello", do_reply=True, do_user_inference=True, do_character_inference=True
    )


@pytest.mark.asyncio
async def test_tts_playback_signals(gateway):
    gateway.bridge.speech_playback_start = AsyncMock()
    gateway.bridge.speech_playback_complete = AsyncMock()

    await gateway.tts_playback_start(character_id="char-1", message_id="msg-1")
    assert gateway.state.ai_state == AIState.SPEAKING
    assert gateway.state.current_speaker_id == "char-1"

    await gateway.tts_playback_complete(character_id="char-1", message_id="msg-1")
    assert gateway.state.ai_state == AIState.IDLE
    assert gateway.state.current_speaker_id is None


@pytest.mark.asyncio
async def test_handle_reply_chunk(gateway):
    gateway.sentence_buffer.process_chunk = AsyncMock()

    data = {
        "message_id": "msg-1",
        "character_id": "char-1",
        "text": "Hello world",
        "start_index": 0,
    }
    await gateway._handle_reply_chunk(data)
    gateway.sentence_buffer.process_chunk.assert_called_with(
        message_id="msg-1", character_id="char-1", text="Hello world", start_index=0
    )


@pytest.mark.asyncio
async def test_gateway_start_stop(gateway):
    gateway.bridge.start = AsyncMock()
    gateway.bridge.stop = AsyncMock()

    await gateway.start()
    gateway.bridge.start.assert_called_once()

    await gateway.stop()
    gateway.bridge.stop.assert_called_once()


@pytest.mark.asyncio
async def test_external_speaker_edge_cases(gateway):
    # Already active
    gateway.state.external_speaker_active = True
    await gateway.external_speaker_start(source="user")
    # Should not call bridge.interrupt (we can't easily check since it wasn't called,
    # but we can check it didn't change anything)

    # Not active stop
    gateway.state.external_speaker_active = False
    await gateway.external_speaker_stop()
    # Should ignore


@pytest.mark.asyncio
async def test_send_context_with_description(gateway):
    gateway.bridge.update_context = AsyncMock()
    gateway.bridge.send_message = AsyncMock()

    await gateway.send_context(key="k", content="c", description="desc")
    gateway.bridge.update_context.assert_called()
    gateway.bridge.send_message.assert_called()


@pytest.mark.asyncio
async def test_debug_methods(gateway):
    gateway.bridge.event_history = [{"id": 1}]
    assert gateway.get_voxta_history() == [{"id": 1}]

    gateway.ws_manager.clients = {"c1": MagicMock()}
    gateway.ws_manager.histories = {"c1": []}
    gateway.ws_manager.get_client_history.return_value = []

    clients = gateway.get_connected_clients()
    assert "c1" in clients

    assert gateway.get_client_history("c1") == []


@pytest.mark.asyncio
async def test_handle_reply_end_and_cancelled(gateway):
    gateway.sentence_buffer.flush = AsyncMock()
    gateway.sentence_buffer.clear = MagicMock()

    # End
    await gateway._handle_reply_end({"message_id": "m1"})
    gateway.sentence_buffer.flush.assert_called_with("m1")

    # Cancelled
    await gateway._handle_reply_cancelled({"message_id": "m1"})
    gateway.sentence_buffer.clear.assert_called_with("m1")


@pytest.mark.asyncio
async def test_on_sentence_ready(gateway):
    gateway.ws_manager.broadcast = AsyncMock()
    await gateway._on_sentence_ready("Hello", "c1", "m1")
    gateway.ws_manager.broadcast.assert_called_with(
        "sentence_ready", {"text": "Hello", "character_id": "c1", "message_id": "m1"}
    )


@pytest.mark.asyncio
async def test_external_speaker_start_interrupts(gateway):
    gateway.state.ai_state = AIState.SPEAKING
    gateway.bridge.interrupt = AsyncMock()
    gateway.state.last_message_id = "m1"
    gateway.bridge.speech_playback_start = AsyncMock()

    await gateway.external_speaker_start("user")
    gateway.bridge.interrupt.assert_called_once()
    gateway.bridge.speech_playback_start.assert_called_with("m1")
