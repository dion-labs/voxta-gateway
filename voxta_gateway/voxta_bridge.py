"""
Voxta Bridge - State Observer for the VoxtaClient.

This module wraps the VoxtaClient and observes Voxta events to update
the Gateway's mirrored state. It is purely observational - it updates
state but never makes decisions based on state.
"""

import asyncio
import contextlib
import logging
from collections import deque
from typing import TYPE_CHECKING, Any

from voxta_client import VoxtaClient
from voxta_client.constants import EventType

from voxta_gateway.event_emitter import EventEmitter
from voxta_gateway.state import AIState, CharacterInfo, GatewayState

if TYPE_CHECKING:
    pass


class VoxtaBridge:
    """
    Wrapper around VoxtaClient that observes state and forwards to Gateway.

    The Bridge is responsible for:
    1. Connecting to Voxta and maintaining connection
    2. Observing Voxta events and updating GatewayState
    3. Forwarding raw events for history/debugging
    4. Providing low-level operations for Gateway actions
    """

    def __init__(
        self,
        voxta_url: str,
        state: GatewayState,
        event_emitter: EventEmitter,
        logger: logging.Logger | None = None,
    ):
        self.voxta_url = voxta_url
        self.state = state
        self.event_emitter = event_emitter
        self.logger = logger or logging.getLogger("VoxtaBridge")

        self.client: VoxtaClient | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._running = False

        # Event history for debugging
        self.event_history: deque[dict] = deque(maxlen=500)

    async def start(self):
        """Start the bridge and connect to Voxta."""
        self._running = True
        await self._connect()

    async def stop(self):
        """Stop the bridge and disconnect from Voxta."""
        self._running = False
        if self._reconnect_task:
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconnect_task

        if self.client:
            await self.client.close()
            self.client = None

        self.state.reset()

    async def _connect(self):
        """Establish connection to Voxta."""
        while self._running:
            try:
                self.logger.info(f"Connecting to Voxta at {self.voxta_url}")
                self.client = VoxtaClient(self.voxta_url)
                self._setup_observers()

                # Negotiate and connect
                connection_token, cookies = self.client.negotiate()

                if not connection_token:
                    raise ConnectionError("Failed to negotiate with Voxta")

                await self.client.connect(connection_token, cookies)
                self.state.connected = True

                self.logger.info("Connected to Voxta")
                await self.event_emitter.emit("voxta_connected", {})

                # Keep running until disconnected
                while self.client and self.client.running and self._running:
                    await asyncio.sleep(1)

            except Exception as e:
                self.logger.error(f"Voxta connection error: {e}")

            # Handle disconnection
            self.state.reset()
            await self.event_emitter.emit("voxta_disconnected", {})

            if self._running:
                self.logger.info("Reconnecting in 5 seconds...")
                await asyncio.sleep(5)

    def _setup_observers(self):
        """Set up event observers on the VoxtaClient."""
        if not self.client:
            return

        # Session/Chat events
        self.client.on(EventType.READY, self._on_ready)
        self.client.on(EventType.CHAT_STARTED, self._on_chat_started)
        self.client.on(EventType.CHAT_CLOSED, self._on_chat_closed)
        self.client.on(EventType.CHAT_PARTICIPANTS_UPDATED, self._on_participants_updated)

        # Reply/Generation events
        self.client.on(EventType.REPLY_GENERATING, self._on_reply_generating)
        self.client.on(EventType.REPLY_START, self._on_reply_start)
        self.client.on(EventType.REPLY_CHUNK, self._on_reply_chunk)
        self.client.on(EventType.REPLY_END, self._on_reply_end)
        self.client.on(EventType.REPLY_CANCELLED, self._on_reply_cancelled)

        # Message events
        self.client.on(EventType.MESSAGE, self._on_message)
        self.client.on(EventType.UPDATE, self._on_message_update)

        # Speech events
        self.client.on(EventType.SPEECH_PLAYBACK_START, self._on_speech_playback_start)
        self.client.on(EventType.SPEECH_PLAYBACK_COMPLETE, self._on_speech_playback_complete)
        self.client.on(EventType.INTERRUPT_SPEECH, self._on_interrupt_speech)

        # Action events
        self.client.on(EventType.ACTION, self._on_action)

        # Outgoing message logging
        self.client.on("client_send", self._on_client_send)

        # Generic handler for all events (for history)
        for event_type in [
            EventType.WELCOME,
            EventType.READY,
            EventType.CHAT_STARTED,
            EventType.CHAT_PARTICIPANTS_UPDATED,
            EventType.REPLY_GENERATING,
            EventType.REPLY_START,
            EventType.REPLY_CHUNK,
            EventType.REPLY_END,
            EventType.REPLY_CANCELLED,
            EventType.MESSAGE,
            EventType.UPDATE,
            EventType.SPEECH_PLAYBACK_START,
            EventType.SPEECH_PLAYBACK_COMPLETE,
            EventType.INTERRUPT_SPEECH,
            EventType.ACTION,
            EventType.ERROR,
        ]:
            self.client.on(event_type, self._record_event)

    async def _record_event(self, data: Any):
        """Record event to history for debugging."""
        import time

        event_type = data.get("$type", "unknown") if isinstance(data, dict) else "unknown"
        self.event_history.append(
            {
                "direction": "IN",
                "type": event_type,
                "data": data if isinstance(data, dict) else {"value": data},
                "timestamp": time.time(),
            }
        )

    async def _on_client_send(self, data: dict):
        """Record outgoing messages to history."""
        import time

        event_type = data.get("$type", "unknown")
        self.event_history.append(
            {
                "direction": "OUT",
                "type": event_type,
                "data": data,
                "timestamp": time.time(),
            }
        )

    # ─────────────────────────────────────────────────────────────
    # State Update Observers
    # ─────────────────────────────────────────────────────────────

    async def _on_ready(self, session_id: Any):
        """Handle ready event - session is established."""
        if isinstance(session_id, str):
            self.state.session_id = session_id
        elif isinstance(session_id, dict):
            self.state.session_id = session_id.get("sessionId") or session_id.get("value")
        self.state.connected = True
        self.logger.info(f"Voxta session ready: {self.state.session_id}")

    async def _on_chat_started(self, data: dict):
        """Handle chat started event."""
        self.state.chat_id = data.get("chatId")
        self.state.session_id = data.get("sessionId") or self.state.session_id

        # Extract characters from context
        context = data.get("context", {})
        characters = context.get("characters", [])

        self.state.characters.clear()
        for char_data in characters:
            char_id = char_data.get("id")
            if char_id:
                self.state.characters[char_id] = CharacterInfo(
                    id=char_id,
                    name=char_data.get("name", "Unknown"),
                    creator_notes=char_data.get("creatorNotes"),
                    text_gen_service=char_data.get("textGenService"),
                )

        self.logger.info(
            f"Chat started: {self.state.chat_id} with {len(self.state.characters)} characters"
        )

        # Notify clients that a chat is now active
        await self.event_emitter.emit(
            "chat_started",
            {"characters": [c.to_dict() for c in self.state.characters.values()]},
        )

        await self.event_emitter.emit(
            "characters_updated",
            {"characters": [c.to_dict() for c in self.state.characters.values()]},
        )

    async def _on_chat_closed(self, data: dict):
        """Handle chat closed event."""
        closed_chat_id = data.get("chatId")

        # Only process if this is our active chat
        if closed_chat_id == self.state.chat_id:
            self.logger.info(f"Chat closed: {closed_chat_id}")

            # Clear chat state
            self.state.chat_id = None
            self.state.characters.clear()
            self.state.ai_state = AIState.IDLE
            self.state.current_speaker_id = None
            self.state.external_speaker_active = False
            self.state.external_speaker_source = None

            # Notify clients that chat is no longer active
            await self.event_emitter.emit("chat_closed", {})

    async def _on_participants_updated(self, data: dict):
        """Handle participant updates."""
        participants = data.get("participants", [])

        # Update characters if we have participant details
        for participant in participants:
            char_id = participant.get("characterId")
            if char_id and char_id not in self.state.characters:
                self.state.characters[char_id] = CharacterInfo(
                    id=char_id,
                    name=participant.get("name", "Unknown"),
                )

        await self.event_emitter.emit(
            "characters_updated",
            {"characters": [c.to_dict() for c in self.state.characters.values()]},
        )

    async def _on_reply_generating(self, _: dict):
        """Handle reply generation starting."""
        old_state = self.state.ai_state
        self.state.ai_state = AIState.THINKING

        if old_state != AIState.THINKING:
            await self.event_emitter.emit(
                "ai_state_changed",
                {"old_state": old_state.value, "new_state": AIState.THINKING.value},
            )

    async def _on_reply_start(self, data: dict):
        """Handle reply start (first chunk about to come)."""
        message_id = data.get("messageId")
        character_id = data.get("senderId")

        self.state.last_message_id = message_id
        self.state.current_speaker_id = character_id

        await self.event_emitter.emit(
            "reply_start",
            {"message_id": message_id, "character_id": character_id},
        )

    async def _on_reply_chunk(self, data: dict):
        """Handle reply text chunk."""
        message_id = data.get("messageId")
        character_id = data.get("senderId")
        text = data.get("text", "")
        start_index = data.get("startIndex", 0)

        await self.event_emitter.emit(
            "reply_chunk",
            {
                "message_id": message_id,
                "character_id": character_id,
                "text": text,
                "start_index": start_index,
            },
        )

    async def _on_reply_end(self, data: dict):
        """Handle reply generation ending."""
        message_id = data.get("messageId")

        await self.event_emitter.emit("reply_end", {"message_id": message_id})

    async def _on_reply_cancelled(self, data: dict):
        """Handle reply cancellation."""
        old_state = self.state.ai_state
        self.state.ai_state = AIState.IDLE

        if old_state != AIState.IDLE:
            await self.event_emitter.emit(
                "ai_state_changed",
                {"old_state": old_state.value, "new_state": AIState.IDLE.value},
            )

        await self.event_emitter.emit("reply_cancelled", {"message_id": data.get("messageId")})

    async def _on_message(self, data: dict):
        """Handle complete message received."""
        message_id = data.get("messageId")
        text = data.get("text", "")
        sender_id = data.get("senderId")
        role = data.get("role", "")

        self.state.last_message_id = message_id
        self.state.last_message_text = text

        # Determine source based on role
        source = "ai" if role.lower() == "assistant" else "user"

        await self.event_emitter.emit(
            "dialogue_received",
            {
                "message_id": message_id,
                "text": text,
                "character_id": sender_id,
                "source": source,
                "author": None,
            },
        )

    async def _on_message_update(self, data: dict):
        """Handle message update (streaming text update)."""
        text = data.get("text", "")
        self.state.last_message_text = text

    async def _on_speech_playback_start(self, _: dict):
        """Handle speech playback starting."""
        old_state = self.state.ai_state
        self.state.ai_state = AIState.SPEAKING

        if old_state != AIState.SPEAKING:
            await self.event_emitter.emit(
                "ai_state_changed",
                {"old_state": old_state.value, "new_state": AIState.SPEAKING.value},
            )

    async def _on_speech_playback_complete(self, _: dict):
        """Handle speech playback completion."""
        old_state = self.state.ai_state
        self.state.ai_state = AIState.IDLE
        self.state.current_speaker_id = None

        if old_state != AIState.IDLE:
            await self.event_emitter.emit(
                "ai_state_changed",
                {"old_state": old_state.value, "new_state": AIState.IDLE.value},
            )

    async def _on_interrupt_speech(self, _: dict):
        """Handle speech interruption."""
        old_state = self.state.ai_state
        self.state.ai_state = AIState.IDLE
        self.state.current_speaker_id = None

        if old_state != AIState.IDLE:
            await self.event_emitter.emit(
                "ai_state_changed",
                {"old_state": old_state.value, "new_state": AIState.IDLE.value},
            )

    async def _on_action(self, data: dict):
        """Handle action/trigger from Voxta."""
        action_name = data.get("value", "")
        arguments = data.get("arguments", [])
        sender_id = data.get("senderId")

        # Convert arguments list to dict if needed
        args_dict = {}
        if isinstance(arguments, list):
            for arg in arguments:
                if isinstance(arg, dict):
                    args_dict.update(arg)
        elif isinstance(arguments, dict):
            args_dict = arguments

        await self.event_emitter.emit(
            "app_trigger",
            {"name": action_name, "arguments": args_dict, "character_id": sender_id},
        )

    # ─────────────────────────────────────────────────────────────
    # Low-Level Operations (for Gateway to call)
    # ─────────────────────────────────────────────────────────────

    async def interrupt(self):
        """Send interrupt command to Voxta."""
        if self.client and self.state.session_id:
            await self.client.interrupt(self.state.session_id)

    async def send_message(
        self,
        text: str,
        do_reply: bool = True,
        do_user_inference: bool = True,
        do_character_inference: bool = True,
    ):
        """Send a message to Voxta."""
        if self.client and self.state.session_id:
            await self.client.send_message(
                text=text,
                session_id=self.state.session_id,
                do_reply=do_reply,
                do_user_inference=do_user_inference,
                do_character_inference=do_character_inference,
            )

    async def speech_playback_start(self, message_id: str | None = None):
        """Notify Voxta that speech playback started."""
        if self.client and self.state.session_id:
            msg_id = message_id or self.state.last_message_id
            await self.client.speech_playback_start(
                session_id=self.state.session_id, message_id=msg_id
            )

    async def speech_playback_complete(self, message_id: str | None = None):
        """Notify Voxta that speech playback completed."""
        if self.client and self.state.session_id:
            msg_id = message_id or self.state.last_message_id
            await self.client.speech_playback_complete(
                session_id=self.state.session_id, message_id=msg_id
            )

    async def character_speech_request(self, character_id: str | None = None, text: str = ""):
        """Request a character to speak."""
        if self.client and self.state.session_id:
            char_id = character_id or self.state.get_first_character_id()
            if char_id:
                await self.client.character_speech_request(
                    character_id=char_id, session_id=self.state.session_id, text=text
                )

    async def update_context(
        self,
        context_key: str,
        contexts: list[dict[str, Any]] | None = None,
        actions: list[dict[str, Any]] | None = None,
        events: list[dict[str, Any]] | None = None,
        set_flags: list[str] | None = None,
        enable_roles: dict[str, bool] | None = None,
    ):
        """Update session context."""
        if self.client and self.state.session_id:
            await self.client.update_context(
                session_id=self.state.session_id,
                context_key=context_key,
                contexts=contexts,
                actions=actions,
                events=events,
                set_flags=set_flags,
                enable_roles=enable_roles,
            )
