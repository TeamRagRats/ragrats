from __future__ import annotations

# Qwen3-Embedding-4B inference for late chunking (voyage) and single-chunk (email).
#
# Late chunking (Günther et al., 2024):
#   1. Tokenise the full text as one sequence.
#   2. Run a single forward pass to get token-level embeddings (last hidden state).
#   3. Mean-pool token embeddings within each paragraph's token span.
# This gives every chunk a context-aware embedding without re-encoding per chunk.
#
# Email summaries are short enough for one chunk: mean-pool over all tokens.

import numpy as np
import torch

from step_09_chunk.chunker import annotate_spans, split_paragraphs, truncate_to_context

DEFAULT_MODEL = "Qwen/Qwen3-Embedding-4B"


def load_model(model_name: str = DEFAULT_MODEL):
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    model = AutoModel.from_pretrained(model_name, trust_remote_code=True)
    model.eval()
    if torch.cuda.is_available():
        model = model.cuda()
    return model, tokenizer


def _mean_pool(token_embeddings: torch.Tensor, start: int, end: int) -> np.ndarray:
    return token_embeddings[start:end].mean(dim=0).cpu().float().numpy()


def late_chunk_voyage(
    text: str,
    model,
    tokenizer,
) -> list[dict]:
    """
    Late chunking for a voyage summary.
    Returns a list of chunk dicts: {chunk_index, text, embedding, char_count}.
    """
    paragraphs = split_paragraphs(text)
    paragraphs = truncate_to_context(paragraphs, tokenizer)
    if not paragraphs:
        return []

    spans = annotate_spans(paragraphs, tokenizer)
    all_ids = []
    for para in paragraphs:
        all_ids.extend(tokenizer.encode(para, add_special_tokens=False))

    input_ids = torch.tensor([all_ids])
    if next(model.parameters()).is_cuda:
        input_ids = input_ids.cuda()

    with torch.no_grad():
        outputs = model(input_ids, output_hidden_states=True)

    token_embeddings = outputs.last_hidden_state[0]  # (seq_len, hidden_size)

    chunks = []
    for i, (para, (start, end)) in enumerate(zip(paragraphs, spans)):
        embedding = _mean_pool(token_embeddings, start, end)
        chunks.append({
            "chunk_index": i,
            "text": para,
            "embedding": embedding,
            "char_count": len(para),
        })
    return chunks


def embed_email(text: str, model, tokenizer) -> dict:
    """
    Single-chunk embedding for an email summary.
    Mean-pools all token embeddings — equivalent to late chunking with one chunk.
    """
    ids = tokenizer.encode(text, add_special_tokens=False)
    input_ids = torch.tensor([ids])
    if next(model.parameters()).is_cuda:
        input_ids = input_ids.cuda()

    with torch.no_grad():
        outputs = model(input_ids, output_hidden_states=True)

    token_embeddings = outputs.last_hidden_state[0]
    embedding = token_embeddings.mean(dim=0).cpu().float().numpy()
    return {
        "chunk_index": 0,
        "text": text,
        "embedding": embedding,
        "char_count": len(text),
    }
