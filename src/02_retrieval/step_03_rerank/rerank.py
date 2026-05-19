from __future__ import annotations

from dataclasses import replace

from step_02_chunk_retrieval.retrieve_vector import RetrievedChunk

from clients.rerank_client import RerankClient

DEFAULT_RERANK_OVERSAMPLE = 3


def rerank_chunks(
    client: RerankClient,
    query: str,
    chunks: list[RetrievedChunk],
    top_k: int,
) -> list[RetrievedChunk]:
    """Reorder `chunks` by reranker relevance and truncate to top_k.

    The reranker receives the ORIGINAL user query (no LLM reformulation) and
    every chunk's `text`. Returned chunks carry `similarity = rerank_score`
    (same overload pattern as BM25 -> ts_rank); indices not returned by the
    reranker are dropped.
    """
    if not chunks:
        return []

    scored = client.rerank(query=query, documents=[c.text for c in chunks])
    if not scored:
        return chunks[:top_k]

    reranked: list[RetrievedChunk] = []
    for idx, score in scored[:top_k]:
        if 0 <= idx < len(chunks):
            reranked.append(replace(chunks[idx], similarity=score))
    return reranked
