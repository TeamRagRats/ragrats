from __future__ import annotations

from typing import Literal

import psycopg

from .retrieve_vector import RetrievedChunk, retrieve_chunks
from .fuse_scores import rrf_fuse
from .bm25.score_bm25 import bm25_retrieve
from .tsrank.score_tsrank import tsrank_retrieve

Mode = Literal["hybrid", "tsrank_only", "bm25_only"]
Lexical = Literal["tsrank", "bm25"]


def hybrid_retrieve_chunks(
    conn: psycopg.Connection,
    query_text: str,
    query_embedding: list[float],
    top_k: int = 20,
    voyage_keys: list[str] | None = None,
    source_types: list[str] | None = None,
    strategies: list[str] | None = None,
    chunkers: list[str] | None = None,
    rrf_k: int = 60,
    mode: Mode = "hybrid",
    lexical: Lexical = "bm25",
    ef_search: int | None = None,
) -> list[RetrievedChunk]:
    """Hybrid retrieval: vector + lexical fused via RRF.

    - query_text: ORIGINAL user query (no LLM reformulation) — fed to the
      lexical retriever.
    - query_embedding: embedding of the (optionally reformulated) query —
      fed to the vector retriever.
    - strategies: forwarded to both retrievers. Defaults to all four chunk
      strategies (context, plain, late, summary).
    - mode='tsrank_only': skip the vector side, return ts_rank results only
      (diagnostic / legacy comparison).
    - mode='bm25_only': skip the vector side, return real BM25 results only
      (diagnostic).
    - lexical: which lexical retriever to use in the 'hybrid' mode. Defaults
      to 'bm25' (real BM25 via pg_search). 'tsrank' falls back to the legacy
      ts_rank path for A/B comparison.

    Returns the same list[RetrievedChunk] shape as retrieve_chunks() so
    downstream loggers / expanders are oblivious to which path produced
    the result.
    """
    if mode == "tsrank_only":
        return tsrank_retrieve(
            conn, query_text, top_k=top_k,
            voyage_keys=voyage_keys, source_types=source_types,
            strategies=strategies, chunkers=chunkers,
        )

    if mode == "bm25_only":
        return bm25_retrieve(
            conn, query_text, top_k=top_k,
            voyage_keys=voyage_keys, source_types=source_types,
            strategies=strategies, chunkers=chunkers,
        )

    lexical_fn = bm25_retrieve if lexical == "bm25" else tsrank_retrieve
    lexical_pool = max(top_k, 2 * top_k)
    lexical_hits = lexical_fn(
        conn, query_text, top_k=lexical_pool,
        voyage_keys=voyage_keys, source_types=source_types,
        strategies=strategies, chunkers=chunkers,
    )

    vector_pool = max(top_k, 2 * top_k)
    vector_hits = retrieve_chunks(
        conn, query_embedding,
        voyage_keys=voyage_keys, top_k=vector_pool,
        source_types=source_types, strategies=strategies, chunkers=chunkers,
        ef_search=ef_search,
    )

    return rrf_fuse(vector_hits, lexical_hits, top_k=top_k, rrf_k=rrf_k)
