"""Tests for the SentenceBuffer module."""

import pytest

from voxta_gateway.sentence_buffer import SentenceBuffer


class TestSentenceBuffer:
    """Tests for the SentenceBuffer class."""

    @pytest.fixture
    def sentences(self):
        """Storage for emitted sentences."""
        return []

    @pytest.fixture
    def buffer(self, sentences):
        """Create a SentenceBuffer that stores to sentences list."""

        async def on_sentence(text, character_id, message_id):
            sentences.append(
                {
                    "text": text,
                    "character_id": character_id,
                    "message_id": message_id,
                }
            )

        return SentenceBuffer(on_sentence)

    @pytest.mark.asyncio
    async def test_single_sentence(self, buffer, sentences):
        """Test processing a single complete sentence."""
        await buffer.process_chunk("msg-1", "char-1", "Hello world! ")

        assert len(sentences) == 1
        assert sentences[0]["text"] == "Hello world!"

    @pytest.mark.asyncio
    async def test_multiple_sentences_one_chunk(self, buffer, sentences):
        """Test multiple sentences in a single chunk."""
        await buffer.process_chunk("msg-1", "char-1", "Hello! How are you? I'm fine. ")

        assert len(sentences) == 3
        assert sentences[0]["text"] == "Hello!"
        assert sentences[1]["text"] == "How are you?"
        assert sentences[2]["text"] == "I'm fine."

    @pytest.mark.asyncio
    async def test_incremental_chunks(self, buffer, sentences):
        """Test processing incremental chunks."""
        await buffer.process_chunk("msg-1", "char-1", "Hello, ")
        assert len(sentences) == 0  # No complete sentence yet

        await buffer.process_chunk("msg-1", "char-1", "Hello, how ")
        assert len(sentences) == 0  # Still no complete sentence

        await buffer.process_chunk("msg-1", "char-1", "Hello, how are you? ")
        assert len(sentences) == 1
        assert sentences[0]["text"] == "Hello, how are you?"

    @pytest.mark.asyncio
    async def test_flush_remaining(self, buffer, sentences):
        """Test flushing remaining text."""
        await buffer.process_chunk("msg-1", "char-1", "Hello! Incomplete")

        assert len(sentences) == 1
        assert sentences[0]["text"] == "Hello!"

        await buffer.flush("msg-1")

        assert len(sentences) == 2
        assert sentences[1]["text"] == "Incomplete"

    @pytest.mark.asyncio
    async def test_flush_nonexistent(self, buffer, sentences):
        """Test flushing a message that doesn't exist."""
        await buffer.flush("nonexistent")
        assert len(sentences) == 0

    @pytest.mark.asyncio
    async def test_newline_as_boundary(self, buffer, sentences):
        """Test newline as sentence boundary."""
        await buffer.process_chunk("msg-1", "char-1", "Line one\nLine two\n")

        assert len(sentences) == 2
        assert sentences[0]["text"] == "Line one"
        assert sentences[1]["text"] == "Line two"

    @pytest.mark.asyncio
    async def test_no_duplicate_sentences(self, buffer, sentences):
        """Test that same sentence isn't emitted twice."""
        await buffer.process_chunk("msg-1", "char-1", "Hello! ")
        await buffer.process_chunk("msg-1", "char-1", "Hello! World! ")

        # "Hello!" should only appear once
        hello_count = sum(1 for s in sentences if s["text"] == "Hello!")
        assert hello_count == 1

    @pytest.mark.asyncio
    async def test_multiple_messages(self, buffer, sentences):
        """Test handling multiple message buffers."""
        await buffer.process_chunk("msg-1", "char-1", "From char 1! ")
        await buffer.process_chunk("msg-2", "char-2", "From char 2! ")

        assert len(sentences) == 2

        msg1 = next(s for s in sentences if s["message_id"] == "msg-1")
        msg2 = next(s for s in sentences if s["message_id"] == "msg-2")

        assert msg1["character_id"] == "char-1"
        assert msg2["character_id"] == "char-2"

    def test_clear_specific_buffer(self, buffer):
        """Test clearing a specific buffer."""
        import asyncio

        async def setup():
            await buffer.process_chunk("msg-1", "char-1", "Hello ")
            await buffer.process_chunk("msg-2", "char-2", "World ")

        asyncio.get_event_loop().run_until_complete(setup())

        buffer.clear("msg-1")

        assert not buffer.has_buffer("msg-1")
        assert buffer.has_buffer("msg-2")

    def test_clear_all_buffers(self, buffer):
        """Test clearing all buffers."""
        import asyncio

        async def setup():
            await buffer.process_chunk("msg-1", "char-1", "Hello ")
            await buffer.process_chunk("msg-2", "char-2", "World ")

        asyncio.get_event_loop().run_until_complete(setup())

        buffer.clear()

        assert not buffer.has_buffer("msg-1")
        assert not buffer.has_buffer("msg-2")

    def test_has_buffer(self, buffer):
        """Test has_buffer method."""
        import asyncio

        assert not buffer.has_buffer("msg-1")

        asyncio.get_event_loop().run_until_complete(
            buffer.process_chunk("msg-1", "char-1", "Hello ")
        )

        assert buffer.has_buffer("msg-1")

    def test_get_current_text(self, buffer):
        """Test get_current_text method."""
        import asyncio

        assert buffer.get_current_text("msg-1") == ""

        asyncio.get_event_loop().run_until_complete(
            buffer.process_chunk("msg-1", "char-1", "Hello world")
        )

        assert buffer.get_current_text("msg-1") == "Hello world"
