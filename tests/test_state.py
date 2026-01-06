"""Tests for the GatewayState module."""

from voxta_gateway.state import AIState, CharacterInfo


class TestAIState:
    """Tests for the AIState enum."""

    def test_state_values(self):
        """Verify all state values are correct."""
        assert AIState.IDLE.value == "idle"
        assert AIState.THINKING.value == "thinking"
        assert AIState.SPEAKING.value == "speaking"


class TestCharacterInfo:
    """Tests for the CharacterInfo dataclass."""

    def test_basic_creation(self):
        """Test creating a CharacterInfo with basic fields."""
        char = CharacterInfo(id="char-123", name="Test Character")
        assert char.id == "char-123"
        assert char.name == "Test Character"
        assert char.creator_notes is None
        assert char.text_gen_service is None

    def test_full_creation(self):
        """Test creating a CharacterInfo with all fields."""
        char = CharacterInfo(
            id="char-123",
            name="Test Character",
            creator_notes="Some notes",
            text_gen_service="openai",
        )
        assert char.creator_notes == "Some notes"
        assert char.text_gen_service == "openai"

    def test_to_dict(self):
        """Test dictionary conversion."""
        char = CharacterInfo(id="char-123", name="Test Character")
        result = char.to_dict()
        assert result["id"] == "char-123"
        assert result["name"] == "Test Character"
        assert "creator_notes" in result
        assert "text_gen_service" in result


class TestGatewayState:
    """Tests for the GatewayState dataclass."""

    def test_default_state(self, gateway_state):
        """Test default state values."""
        assert gateway_state.connected is False
        assert gateway_state.session_id is None
        assert gateway_state.chat_id is None
        assert gateway_state.ai_state == AIState.IDLE
        assert gateway_state.external_speaker_active is False
        assert len(gateway_state.characters) == 0

    def test_chat_active_property(self, gateway_state):
        """Test chat_active property."""
        assert gateway_state.chat_active is False

        gateway_state.chat_id = "chat-123"
        assert gateway_state.chat_active is True

        gateway_state.chat_id = None
        assert gateway_state.chat_active is False

    def test_to_snapshot(self, gateway_state):
        """Test snapshot creation."""
        snapshot = gateway_state.to_snapshot()

        assert snapshot["connected"] is False
        assert snapshot["chat_active"] is False
        assert snapshot["ai_state"] == "idle"
        assert snapshot["external_speaker_active"] is False
        assert snapshot["characters"] == []

    def test_to_snapshot_with_characters(self, gateway_state):
        """Test snapshot with characters."""
        gateway_state.characters["char-1"] = CharacterInfo(id="char-1", name="Alice")
        gateway_state.characters["char-2"] = CharacterInfo(id="char-2", name="Bob")

        snapshot = gateway_state.to_snapshot()
        assert len(snapshot["characters"]) == 2

        names = [c["name"] for c in snapshot["characters"]]
        assert "Alice" in names
        assert "Bob" in names

    def test_reset(self, gateway_state):
        """Test state reset."""
        # Set up some state
        gateway_state.connected = True
        gateway_state.session_id = "session-123"
        gateway_state.chat_id = "chat-456"
        gateway_state.ai_state = AIState.SPEAKING
        gateway_state.external_speaker_active = True
        gateway_state.characters["char-1"] = CharacterInfo(id="char-1", name="Alice")

        # Reset
        gateway_state.reset()

        # Verify defaults
        assert gateway_state.connected is False
        assert gateway_state.session_id is None
        assert gateway_state.chat_id is None
        assert gateway_state.ai_state == AIState.IDLE
        assert gateway_state.external_speaker_active is False
        assert len(gateway_state.characters) == 0

    def test_get_first_character_id_empty(self, gateway_state):
        """Test get_first_character_id with no characters."""
        assert gateway_state.get_first_character_id() is None

    def test_get_first_character_id_with_characters(self, gateway_state):
        """Test get_first_character_id with characters."""
        gateway_state.characters["char-1"] = CharacterInfo(id="char-1", name="Alice")
        gateway_state.characters["char-2"] = CharacterInfo(id="char-2", name="Bob")

        result = gateway_state.get_first_character_id()
        assert result in ["char-1", "char-2"]
