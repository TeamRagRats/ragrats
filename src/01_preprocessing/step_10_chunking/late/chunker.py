from __future__ import annotations

import re

MIN_CHUNK_CHARS = 20
MAX_TOKENS = 32768  # Qwen3-Embedding-4B context window


def split_sentences(text: str) -> list[str]:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in sentences if len(s.strip()) >= MIN_CHUNK_CHARS]


def truncate_to_context(
    sentences: list[str],
    tokenizer,
    max_tokens: int = MAX_TOKENS,
) -> list[str]:
    kept: list[str] = []
    total = 0
    for s in sentences:
        n = len(tokenizer.encode(s, add_special_tokens=False))
        if total + n > max_tokens:
            break
        kept.append(s)
        total += n
    return kept
