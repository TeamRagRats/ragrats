from __future__ import annotations

# Pure chunking logic for llm_structured.structured_md.
# No DB access — imported by the late and context embedding runners.
#
# Strategy: fixed-window + overlap.
#   • Target chunk size: TARGET_CHARS
#   • Overlap between consecutive chunks: OVERLAP_CHARS
#   • Boundary preference: paragraph break > line break > sentence end > whitespace
#     within the last LOOKBACK_FRACTION of the window; hard cut if none found.

from dataclasses import dataclass

TARGET_CHARS = 1500    # ≈ 375 tokens at char/4
OVERLAP_CHARS = 200    # ≈ 50 tokens
LOOKBACK_FRACTION = 0.30  # search backwards over last 30% of the window for a break


@dataclass
class Chunk:
    text: str
    chunk_index: int
    section_title: str | None
    char_count: int
    token_estimate: int
    start_offset: int   # inclusive char offset in source text
    end_offset: int     # exclusive char offset in source text


def chunk_structured_md(text: str) -> list[Chunk]:
    """Split structured_md with fixed-window + overlap."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= TARGET_CHARS:
        return [_make_chunk(text, 0, 0, len(text))]

    chunks: list[Chunk] = []
    pos = 0
    n = len(text)

    while pos < n:
        end = pos + TARGET_CHARS
        if end >= n:
            chunks.append(_make_chunk(text[pos:].rstrip(), len(chunks), pos, n))
            break

        cut = _find_break(text, pos, end)
        chunks.append(_make_chunk(text[pos:cut].rstrip(), len(chunks), pos, cut))

        next_pos = cut - OVERLAP_CHARS
        if next_pos <= pos:
            next_pos = cut  # overlap pushed us backwards; advance forcibly
        pos = next_pos

    return chunks


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _make_chunk(text: str, index: int, start: int, end: int) -> Chunk:
    return Chunk(
        text=text,
        chunk_index=index,
        section_title=None,
        char_count=len(text),
        token_estimate=len(text) // 4,
        start_offset=start,
        end_offset=end,
    )


def _find_break(text: str, start: int, end: int) -> int:
    """Return a cut position in (lookback_start, end] preferring natural boundaries.

    Falls back to `end` (hard cut) if no boundary is found in the lookback window.
    """
    lookback_start = end - int((end - start) * LOOKBACK_FRACTION)

    # Paragraph break: prefer the LAST '\n\n' in the lookback window.
    para = text.rfind("\n\n", lookback_start, end)
    if para != -1:
        return para + 2

    # Single newline.
    nl = text.rfind("\n", lookback_start, end)
    if nl != -1:
        return nl + 1

    # Sentence end ('. ', '! ', '? ').
    for marker in (". ", "! ", "? "):
        m = text.rfind(marker, lookback_start, end)
        if m != -1:
            return m + 2

    # Any whitespace.
    ws = text.rfind(" ", lookback_start, end)
    if ws != -1:
        return ws + 1

    # Hard cut.
    return end
