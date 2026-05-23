from __future__ import annotations

from dataclasses import replace

from step_02_chunk_retrieval.retrieve_vector import RetrievedChunk

from clients.rerank_client import RerankClient

DEFAULT_RERANK_OVERSAMPLE = 3

# Qwen3-Reranker-8B has an 8192-token context. We pre-truncate each chunk's
# text by character count so (query + doc) reliably fits. ~4 chars/token is
# a safe rule of thumb for English+Danish; 24000 chars ≈ 6000 tokens, leaving
# ample room for the query.
_MAX_DOC_CHARS = 24000


def rerank_chunks(
    client: RerankClient,
    query: str,
    chunks: list[RetrievedChunk],
    top_k: int,
) -> list[RetrievedChunk]:
    """Reorder `chunks` by Qwen3-Reranker-8B relevance and truncate to top_k.

    The reranker receives the ORIGINAL user query (no LLM reformulation) and
    every chunk's `text`. Returned chunks carry `similarity = rerank_score`
    (same overload pattern as the lexical retrievers overload `similarity`
    with ts_rank / BM25); indices not returned by the reranker are dropped.
    """
    if not chunks:
        return []

    documents = [(c.text or "")[:_MAX_DOC_CHARS] for c in chunks]
    scored = client.rerank(query=query, documents=documents)
    if not scored:
        return chunks[:top_k]

    reranked: list[RetrievedChunk] = []
    for idx, score in scored[:top_k]:
        if 0 <= idx < len(chunks):
            reranked.append(replace(chunks[idx], similarity=score))
    return reranked
