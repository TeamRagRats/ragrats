from __future__ import annotations


def find_tail(text: str) -> str:
    """Return the portion of text starting from the first sentence boundary
    after the midpoint — roughly the last 40-60% of the text."""
    mid = len(text) // 2
    pos = text.find('.', mid)
    if pos == -1 or pos >= len(text) - 1:
        return ""
    return text[pos + 1:].strip()


def build_overlap_chunks(phases: list[dict]) -> list[dict]:
    """Build overlap chunks from a list of phases for one voyage.

    phases: [{"phase_index": int, "summary": str}] sorted by phase_index ASC.

    Chunk N = tail of phase N-1 + full summary of phase N.
    Chunk 0 = full summary of phase 0 only (no predecessor).
    """
    chunks = []
    prev_tail = ""
    for phase in phases:
        summary = phase["summary"]
        text = (prev_tail + "\n\n" + summary).strip() if prev_tail else summary
        chunks.append({
            "chunk_index": phase["phase_index"],
            "text": text,
            "char_count": len(text),
        })
        prev_tail = find_tail(summary)
    return chunks
