from __future__ import annotations

# Local model loading and per-token embedding extraction for late chunking.
# Loads Qwen3-Embedding-4B directly via HuggingFace — no embedding server needed.
# Shared embedding model loader used by every email/attachment embedding runner.

import torch
from transformers import AutoModel


def load_model(device: str = "cuda") -> AutoModel:
    model = AutoModel.from_pretrained(
        "Qwen/Qwen3-Embedding-4B",
        torch_dtype=torch.float16,
        trust_remote_code=True,
    )
    model.to(device).eval()
    return model


def get_token_embeddings(
    model: AutoModel,
    tokenizer,
    text: str,
    device: str,
    max_length: int = 32768,
) -> list[list[float]]:
    """Run a forward pass on text and return per-token hidden states.

    Returns list[list[float]] of shape [seq_len, 2560].
    seq_len is clamped to max_length by the tokenizer truncation.
    """
    encoded = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=max_length,
        return_offsets_mapping=False,
    ).to(device)

    with torch.no_grad():
        out = model(**encoded, output_hidden_states=False)

    hidden = out.last_hidden_state.squeeze(0).to(torch.float32).cpu()
    return hidden.tolist()
