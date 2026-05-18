from __future__ import annotations

from typing import Literal

import psycopg

from step_02_chunk_retrieval.retrieve_chunks import RetrievedChunk, retrieve_chunks

from .fuse_scores import rrf_fuse
from .score_bm25 import bm25_retrieve

Mode = Literal["hybrid", "bm25_only"]


def hybrid_retrieve_chunks(
    conn: psycopg.Connection,
    query_text: str,
    query_embedding: list[float],
    top_k: int = 20,
    voyage_keys: list[str] | None = None,
    source_types: list[str] | None = None,
    strategies: list[str] | None = None,
    rrf_k: int = 60,
    mode: Mode = "hybrid",
    ef_search: int | None = None,
) -> list[RetrievedChunk]:
    """Hybrid retrieval: vector + BM25 fused via RRF.

    - query_text: ORIGINAL user query (no LLM reformulation) — fed to BM25.
    - query_embedding: embedding of the (optionally reformulated) query —
      fed to the vector retriever.
    - strategies: forwarded to both the vector retriever and BM25. Defaults
      to all four strategies (context, plain, late, summary).
    - mode='bm25_only': skip the vector side entirely (diagnostic).

    Returns the same list[RetrievedChunk] shape as retrieve_chunks() so
    downstream loggers / expanders are oblivious to which path produced
    the result.
    """
    bm25_pool = max(top_k, 2 * top_k)
    bm25_hits = bm25_retrieve(
        conn, query_text, top_k=bm25_pool,
        voyage_keys=voyage_keys, source_types=source_types,
        strategies=strategies,
    )

    if mode == "bm25_only":
        return bm25_hits[:top_k]

    vector_pool = max(top_k, 2 * top_k)
    vector_hits = retrieve_chunks(
        conn, query_embedding,
        voyage_keys=voyage_keys, top_k=vector_pool,
        source_types=source_types, strategies=strategies,
        ef_search=ef_search,
    )

    return rrf_fuse(vector_hits, bm25_hits, top_k=top_k, rrf_k=rrf_k)
