"""
Sentence Buffer - Processes reply chunks into complete sentences.

This module accumulates text chunks from Voxta's streaming replies and
emits complete sentences suitable for TTS processing. It handles the
complexity of sentence boundary detection so downstream apps don't have to.
"""

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

# Type alias for sentence callback
SentenceCallback = Callable[[str, str, str], Awaitable[None]]


@dataclass
class MessageBuffer:
    """Buffer for accumulating text chunks of a single message."""

    message_id: str
    character_id: str
    text: str = ""
    processed_len: int = 0
    emitted_sentences: set[str] = field(default_factory=set)


class SentenceBuffer:
    """
    Accumulates streaming reply chunks and emits complete sentences.

    This is useful for TTS systems that need complete sentences rather
    than character-by-character streaming.

    Usage:
        async def on_sentence(text, character_id, message_id):
            print(f"Sentence ready: {text}")

        buffer = SentenceBuffer(on_sentence)

        # As chunks arrive from Voxta:
        await buffer.process_chunk("msg-1", "char-1", "Hello, ")
        await buffer.process_chunk("msg-1", "char-1", "how are you? I'm doing")
        # on_sentence called with "Hello, how are you?"

        # When reply ends:
        await buffer.flush("msg-1")
        # on_sentence called with "I'm doing" (remaining text)
    """

    # Sentence-ending patterns
    # Matches: .!? followed by space/newline, or just newline
    SENTENCE_PATTERN = re.compile(r"([.!?]+\s+|\n)")

    def __init__(self, on_sentence: SentenceCallback):
        """
        Initialize the sentence buffer.

        Args:
            on_sentence: Async callback called with (text, character_id, message_id)
                         for each complete sentence.
        """
        self.buffers: dict[str, MessageBuffer] = {}
        self.on_sentence = on_sentence

    async def process_chunk(
        self,
        message_id: str,
        character_id: str,
        text: str,
        start_index: int = 0,
    ):
        """
        Process an incoming text chunk.

        Args:
            message_id: The message this chunk belongs to
            character_id: The character speaking
            text: The text content (may be cumulative or incremental)
            start_index: If >0, indicates this is an update starting at this position
        """
        # Get or create buffer for this message
        if message_id not in self.buffers:
            self.buffers[message_id] = MessageBuffer(
                message_id=message_id,
                character_id=character_id,
            )

        buf = self.buffers[message_id]

        # Handle text accumulation
        # Voxta can send either:
        # 1. Complete cumulative text (start_index=0, text grows)
        # 2. Incremental updates (start_index indicates position)
        if start_index == 0:
            # Cumulative mode - text is the complete message so far
            if len(text) >= len(buf.text):
                buf.text = text
        elif start_index <= len(buf.text):
            # Replacement at position
            buf.text = buf.text[:start_index] + text
        else:
            # Append (gap in indices, just append)
            buf.text += text

        # Extract and emit complete sentences
        await self._extract_sentences(buf)

    async def _extract_sentences(self, buf: MessageBuffer):
        """Extract complete sentences from the buffer."""
        # Only process text we haven't looked at yet
        unprocessed = buf.text[buf.processed_len :]

        # Split on sentence boundaries
        parts = self.SENTENCE_PATTERN.split(unprocessed)

        # Process pairs of (sentence, delimiter) except the last unpaired part
        # Example: "Hello! How are you? I'm" -> ["Hello", "! ", "How are you", "? ", "I'm"]
        # We process: "Hello! " and "How are you? " but leave "I'm" for later

        if len(parts) > 1:
            i = 0
            while i < len(parts) - 1:
                # Combine content with its delimiter
                content = parts[i]
                delimiter = parts[i + 1] if i + 1 < len(parts) else ""

                sentence = (content + delimiter).strip()

                if sentence and sentence not in buf.emitted_sentences:
                    buf.emitted_sentences.add(sentence)
                    await self.on_sentence(sentence, buf.character_id, buf.message_id)

                # Update processed length
                buf.processed_len += len(content) + len(delimiter)
                i += 2

    async def flush(self, message_id: str):
        """
        Flush any remaining text for a message (call when reply ends).

        Args:
            message_id: The message to flush
        """
        if message_id not in self.buffers:
            return

        buf = self.buffers[message_id]

        # Emit any remaining unprocessed text
        remaining = buf.text[buf.processed_len :].strip()
        if remaining and remaining not in buf.emitted_sentences:
            await self.on_sentence(remaining, buf.character_id, buf.message_id)

        # Clean up
        del self.buffers[message_id]

    def clear(self, message_id: str | None = None):
        """
        Clear buffer(s) without emitting remaining text.

        Args:
            message_id: If provided, clear only that message's buffer.
                       Otherwise, clear all buffers.
        """
        if message_id is None:
            self.buffers.clear()
        elif message_id in self.buffers:
            del self.buffers[message_id]

    def has_buffer(self, message_id: str) -> bool:
        """Check if a buffer exists for a message."""
        return message_id in self.buffers

    def get_current_text(self, message_id: str) -> str:
        """Get the current accumulated text for a message."""
        if message_id in self.buffers:
            return self.buffers[message_id].text
        return ""
