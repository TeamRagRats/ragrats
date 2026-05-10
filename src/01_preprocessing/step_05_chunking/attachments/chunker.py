from __future__ import annotations

# Pure chunking logic for llm_structured.structured_md.
# No DB access — imported by the late and context embedding runners.
#
# Strategy:
#   total_chars ≤ 2048  →  single chunk (whole doc)
#   total_chars > 2048  →  Chunk A: header block (everything before ## Content)
#                          Chunk B+: ## Content section, split at ### boundaries
#                            • merge if < 200 chars into next sibling
#                            • split at paragraph breaks if > 2048 chars
#                          If no ### subsections: paragraph-split at 2048-char ceiling

import re
from dataclasses import dataclass

MAX_CHARS = 2048   # ≈ 512 tokens at char/4
MIN_CHARS = 200    # ≈ 50 tokens — merge if below this


@dataclass
class Chunk:
    text: str
    chunk_index: int
    section_title: str | None
    char_count: int
    token_estimate: int


def chunk_structured_md(text: str) -> list[Chunk]:
    """Split structured_md into chunks using the agreed strategy."""
    text = text.strip()
    if not text:
        return []

    if len(text) <= MAX_CHARS:
        return [_make_chunk(text, 0, None)]

    header, content = _split_at_content(text)
    sections: list[tuple[str | None, str]] = []

    if content is None:
        # No ## Content found — treat whole doc as content, paragraph-split
        sections = [(None, header)]
    else:
        if header.strip():
            sections.append((None, header))

        h3_sections = _split_h3_sections(content)
        if len(h3_sections) > 1:
            h3_sections = _merge_short(h3_sections, MIN_CHARS)
            for title, body in h3_sections:
                if len(body) > MAX_CHARS:
                    for para in _split_paragraphs(body, MAX_CHARS):
                        sections.append((title, para))
                else:
                    sections.append((title, body))
        else:
            # No ### subsections — paragraph-split the content block
            _, flat_content = h3_sections[0]
            for para in _split_paragraphs(flat_content, MAX_CHARS):
                sections.append((None, para))

    chunks: list[Chunk] = []
    for idx, (title, body) in enumerate(sections):
        body = body.strip()
        if body:
            chunks.append(_make_chunk(body, idx, title))

    # Re-index in case empty bodies were dropped
    for i, c in enumerate(chunks):
        c.chunk_index = i

    return chunks


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _make_chunk(text: str, index: int, title: str | None) -> Chunk:
    return Chunk(
        text=text,
        chunk_index=index,
        section_title=title,
        char_count=len(text),
        token_estimate=len(text) // 4,
    )


def _split_at_content(text: str) -> tuple[str, str | None]:
    """Split at the first '## Content' heading.

    Returns (header_block, content_block). content_block is None if the
    heading is absent.
    """
    match = re.search(r"(?m)^## Content\b", text)
    if not match:
        return text, None
    return text[: match.start()].rstrip(), text[match.start():]


def _split_h3_sections(text: str) -> list[tuple[str | None, str]]:
    """Split text at '### ' headings.

    Returns list of (title_or_None, section_text) pairs. The first entry
    may have title=None if text before the first ### is non-empty.
    """
    parts = re.split(r"(?m)^(### .+)$", text)
    # parts alternates: [pre_text, heading, body, heading, body, ...]
    sections: list[tuple[str | None, str]] = []

    pre = parts[0].strip()
    if pre:
        sections.append((None, pre))

    i = 1
    while i < len(parts) - 1:
        heading = parts[i].lstrip("#").strip()
        body = parts[i + 1].strip()
        sections.append((heading, f"### {parts[i].lstrip('# ').strip()}\n\n{body}" if body else f"### {heading}"))
        i += 2

    return sections if sections else [(None, text)]


def _split_paragraphs(text: str, max_chars: int) -> list[str]:
    """Split text at blank lines, respecting max_chars ceiling.

    If a single paragraph exceeds max_chars it is hard-split at the nearest
    whitespace before the limit.
    """
    paragraphs = re.split(r"\n{2,}", text)
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # If para alone exceeds ceiling, hard-split it first
        for segment in _hard_split(para, max_chars):
            if current_len + len(segment) + 2 > max_chars and current_parts:
                chunks.append("\n\n".join(current_parts))
                current_parts = [segment]
                current_len = len(segment)
            else:
                current_parts.append(segment)
                current_len += len(segment) + 2

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return chunks if chunks else [text]


def _hard_split(text: str, max_chars: int) -> list[str]:
    """Hard-split a string that may exceed max_chars into ≤max_chars segments,
    breaking at whitespace where possible."""
    if len(text) <= max_chars:
        return [text]
    segments: list[str] = []
    while len(text) > max_chars:
        split_at = text.rfind(" ", 0, max_chars)
        if split_at == -1:
            split_at = max_chars
        segments.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        segments.append(text)
    return segments


def _merge_short(
    sections: list[tuple[str | None, str]], min_chars: int
) -> list[tuple[str | None, str]]:
    """Merge sections shorter than min_chars into an adjacent sibling.

    Forward pass: accumulate short sections until the combined text reaches
    min_chars, then emit. Any leftover at the end merges into the last emitted
    section.
    """
    if len(sections) <= 1:
        return sections

    merged: list[tuple[str | None, str]] = []
    pending_title: str | None = None
    pending_text: str = ""

    for title, body in sections:
        if pending_text:
            combined_title = pending_title
            combined_text = (pending_text + "\n\n" + body).strip()
        else:
            combined_title = title
            combined_text = body

        if len(combined_text) < min_chars:
            pending_title = combined_title
            pending_text = combined_text
        else:
            merged.append((combined_title, combined_text))
            pending_title = None
            pending_text = ""

    if pending_text:
        if merged:
            prev_title, prev_text = merged[-1]
            merged[-1] = (prev_title, (prev_text + "\n\n" + pending_text).strip())
        else:
            merged.append((pending_title, pending_text))

    return merged
