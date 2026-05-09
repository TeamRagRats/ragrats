from __future__ import annotations

# Single-text embedder: forward pass -> mean-pool over non-pad tokens ->
# L2-normalize. Used by email_context chunking, where the input is
# (prior-thread summary + email body) and we want one vector per email.

import math

import torch


def embed_text(
    model,
    tokenizer,
    text: str,
    device: str,
    max_length: int = 32768,
) -> tuple[list[float], int, bool]:
    """Embed `text` into a single L2-normalized vector via mean pooling.

    Returns (vector, n_tokens, truncated).
    """
    encoded = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=max_length,
        padding=False,
    ).to(device)

    input_ids = encoded["input_ids"]
    attention_mask = encoded.get("attention_mask")
    n_tokens = int(input_ids.shape[1])
    truncated = n_tokens >= max_length

    with torch.no_grad():
        out = model(**encoded, output_hidden_states=False)

    hidden = out.last_hidden_state.squeeze(0).to(torch.float32).cpu()  # [seq, dim]

    if attention_mask is not None:
        mask = attention_mask.squeeze(0).to(torch.float32).cpu()  # [seq]
        denom = float(mask.sum().item()) or 1.0
        pooled = (hidden * mask.unsqueeze(-1)).sum(dim=0) / denom
    else:
        pooled = hidden.mean(dim=0)

    vec = pooled.tolist()
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    vec = [v / norm for v in vec]
    return vec, n_tokens, truncated


def format_halfvec(vec: list[float]) -> str:
    """Format a float vector as Postgres halfvec literal: '[v1,v2,...]'."""
    return "[" + ",".join(f"{v:.7g}" for v in vec) + "]"
