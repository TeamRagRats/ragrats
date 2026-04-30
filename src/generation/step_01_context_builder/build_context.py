from __future__ import annotations


def build_context(chunks: list[dict]) -> str:
    parts: list[str] = []
    for i, c in enumerate(chunks, start=1):
        header = (
            f"[{i}] SOURCE: {c['source_type']} | "
            f"VOYAGE: {c['voyage_key']} | "
            f"SIMILARITY: {round(c['similarity'], 4)}"
        )
        parts.append(f"{header}\n{c['text']}")
    return "\n\n".join(parts)
