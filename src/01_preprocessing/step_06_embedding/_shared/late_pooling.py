from __future__ import annotations

# Token-span pooling for late chunking: map a chunk's char span onto the token
# grid returned by model.get_token_embeddings, then mean-pool those token
# vectors into one chunk embedding. Used by the late-embedding pipeline.


def char_spans_to_token_spans(
    tokenizer,
    full_text: str,
    char_spans: list[tuple[int, int]],
    n_tokens: int,
) -> list[tuple[int, int]]:
    """Map char-level spans to token-level spans using offset_mapping.

    n_tokens is the number of tokens actually returned by the embedding server
    (may be smaller than the tokenizer's view if the server truncated).
    Returned token spans are clamped to [0, n_tokens).
    """
    encoded = tokenizer(
        full_text,
        return_offsets_mapping=True,
        add_special_tokens=True,
        truncation=False,
    )
    offsets: list[tuple[int, int]] = encoded["offset_mapping"]

    token_spans: list[tuple[int, int]] = []
    for char_start, char_end in char_spans:
        tok_start = None
        tok_end = None
        for tok_idx, (a, b) in enumerate(offsets):
            if a == 0 and b == 0:
                continue
            if tok_start is None and b > char_start and a < char_end:
                tok_start = tok_idx
            if a < char_end:
                tok_end = tok_idx + 1
        if tok_start is None or tok_end is None or tok_start >= tok_end:
            tok_start = min(len(offsets), n_tokens)
            tok_end = tok_start
        tok_start = min(tok_start, n_tokens)
        tok_end = min(tok_end, n_tokens)
        token_spans.append((tok_start, tok_end))
    return token_spans


def mean_pool(token_vectors: list[list[float]], span: tuple[int, int]) -> list[float]:
    """Mean-pool token_vectors[start:end]. Returns flat list[float] (length = hidden_dim).

    Falls back to zero vector if span is empty (shouldn't happen for valid input).
    """
    start, end = span
    if end <= start or start >= len(token_vectors):
        hidden = len(token_vectors[0]) if token_vectors else 0
        return [0.0] * hidden
    end = min(end, len(token_vectors))
    n = end - start
    hidden = len(token_vectors[start])
    acc = [0.0] * hidden
    for i in range(start, end):
        row = token_vectors[i]
        for j in range(hidden):
            acc[j] += row[j]
    return [v / n for v in acc]
