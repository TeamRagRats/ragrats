"""Per-question retrieval pipeline for the chunk retrieval test.

reformulate (optional) -> embed -> retrieve (vector | hybrid | bm25-only)
-> rerank (optional). Returns the final chunk list.
"""
from __future__ import annotations

from clients.embed_client import EmbedClient
from clients.llm_client import LLMClient
from clients.rerank_client import RerankClient
from step_00_query_reformulation import reformulate_query
from step_02_chunk_retrieval import retrieve_chunks, hybrid_retrieve_chunks
from step_03_rerank import rerank_chunks


def retrieve_for_question(
    conn,
    *,
    client: EmbedClient,
    llm: LLMClient | None,
    reranker: RerankClient | None,
    question: str,
    expected_key: str,
    top_k: int,
    rerank_pool: int,
    hybrid_mode: str | None,
    rrf_k: int,
    source_types: list[str] | None,
    strategies: list[str] | None,
    ef_search: int | None,
) -> list:
    q = reformulate_query(llm, question) if llm else question
    embedding = client.embed([q])[0]

    step2_top_k = rerank_pool if reranker is not None else top_k
    if hybrid_mode is not None:
        chunks = hybrid_retrieve_chunks(
            conn, query_text=question, query_embedding=embedding,
            voyage_keys=[expected_key], top_k=step2_top_k,
            source_types=source_types, strategies=strategies,
            rrf_k=rrf_k, mode=hybrid_mode,
            ef_search=ef_search,
        )
    else:
        chunks = retrieve_chunks(
            conn, embedding, voyage_keys=[expected_key], top_k=step2_top_k,
            source_types=source_types, strategies=strategies,
            ef_search=ef_search,
        )

    if reranker is not None:
        chunks = rerank_chunks(reranker, question, chunks, top_k=top_k)
    return chunks
