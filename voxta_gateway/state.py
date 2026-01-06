"""
Gateway state model definitions.

The Gateway maintains a mirrored state of the Voxta Brain and broadcasts
state changes to subscribed downstream applications.
"""

from dataclasses import dataclass, field
from enum import Enum


class AIState(Enum):
    """Current state of the AI assistant."""

    IDLE = "idle"
    THINKING = "thinking"  # Generating reply
    SPEAKING = "speaking"  # TTS playing (either Voxta or bridge-controlled)


@dataclass
class CharacterInfo:
    """Information about a character in the chat session."""

    id: str  # noqa: A003
    name: str
    creator_notes: str | None = None
    text_gen_service: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "creator_notes": self.creator_notes,
            "text_gen_service": self.text_gen_service,
        }


@dataclass
class GatewayState:
    """
    Mirrored state of the Voxta Brain.

    This state is observable and broadcastable, but the Gateway should never
    make autonomous decisions based on state. Actions are only taken in
    response to API calls from downstream apps.
    """

    # Connection State
    connected: bool = False
    session_id: str | None = None

    # Chat State
    chat_id: str | None = None
    characters: dict[str, CharacterInfo] = field(default_factory=dict)

    # AI Activity State
    ai_state: AIState = AIState.IDLE
    current_speaker_id: str | None = None
    last_message_id: str | None = None
    last_message_text: str | None = None

    # External Speaker State (game dialogue, user talking, etc.)
    external_speaker_active: bool = False
    external_speaker_source: str | None = None  # "game", "user", etc.

    @property
    def chat_active(self) -> bool:
        """Check if there's an active chat session."""
        return self.chat_id is not None

    def to_snapshot(self) -> dict:
        """
        Create a state snapshot for WebSocket clients.

        This is sent to clients on connection so they don't need to wait
        for state-changing events to know the current state.

        Note: We expose `chat_active` (boolean) instead of `chat_id` to avoid
        leaking internal IDs. Clients only need to know if a chat is active.
        """
        return {
            "connected": self.connected,
            "chat_active": self.chat_active,
            "ai_state": self.ai_state.value,
            "current_speaker_id": self.current_speaker_id,
            "external_speaker_active": self.external_speaker_active,
            "external_speaker_source": self.external_speaker_source,
            "characters": [c.to_dict() for c in self.characters.values()],
        }

    def reset(self):
        """Reset state to defaults (called on Voxta disconnection)."""
        self.connected = False
        self.session_id = None
        self.chat_id = None
        self.characters.clear()
        self.ai_state = AIState.IDLE
        self.current_speaker_id = None
        self.last_message_id = None
        self.last_message_text = None
        self.external_speaker_active = False
        self.external_speaker_source = None

    def get_first_character_id(self) -> str | None:
        """Get the ID of the first character, if any."""
        if self.characters:
            return next(iter(self.characters.keys()))
        return None
