from __future__ import annotations

# Paragraph-based text splitting for late chunking.
# Splits on double newlines (natural semantic boundaries) rather than fixed token windows.
# Justified in thesis by Günther et al. (2024): late chunking benefits from meaningful
# chunk boundaries that align with the text's inherent structure.

MIN_CHUNK_CHARS = 20
MAX_TOKENS = 32768  # Qwen3-Embedding-4B context window


def split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if len(p.strip()) >= MIN_CHUNK_CHARS]


def truncate_to_context(
    paragraphs: list[str],
    tokenizer,
    max_tokens: int = MAX_TOKENS,
) -> list[str]:
    """Drop trailing paragraphs that would push the total token count over the model limit."""
    kept: list[str] = []
    total = 0
    for para in paragraphs:
        n = len(tokenizer.encode(para, add_special_tokens=False))
        if total + n > max_tokens:
            break
        kept.append(para)
        total += n
    return kept
