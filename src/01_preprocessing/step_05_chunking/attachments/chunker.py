from __future__ import annotations

# Attachment chunking entry point. The actual fixed-window + overlap logic
# lives in general_chunker; this just feeds it the attachment's structured_md.

from step_05_chunking.general_chunker.chunker import Chunk, TARGET_CHARS, chunk_text


def chunk_structured_md(text: str, target_chars: int = TARGET_CHARS) -> list[Chunk]:
    """Chunk an attachment's structured_md with the shared fixed-window splitter."""
    return chunk_text(text, target_chars=target_chars)
