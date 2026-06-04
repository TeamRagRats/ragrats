from __future__ import annotations

# Email chunking entry point. Long emails are split the same way as attachments:
# the fixed-window + overlap logic lives in general_chunker; this just feeds it
# the email's body_cleaned. Short emails (<= TARGET_CHARS) yield a single chunk.

from step_05_chunking.general_chunker.chunker import Chunk, TARGET_CHARS, chunk_text


def chunk_email_body(body: str, target_chars: int = TARGET_CHARS) -> list[Chunk]:
    """Chunk an email's body_cleaned with the shared fixed-window splitter."""
    return chunk_text(body, target_chars=target_chars)
