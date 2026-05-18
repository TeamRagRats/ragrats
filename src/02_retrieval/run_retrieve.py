from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent          # src/02_retrieval/
    _repo_root = _here.parents[1]                     # repo root
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_here))                    # step_01_*, step_02_*
    __package__ = "src.retrieval"

import argparse
import json
import logging
import time

from core.db import connect
from log.log_retrieval import log_retrieval
from log.log_query import log_query
from clients.embed_client import EmbedClient, DEFAULT_BASE_URL
from clients.llm_client import LLMClient
from clients.rerank_client import RerankClient, DEFAULT_BASE_URL as DEFAULT_RERANK_URL

from step_00_query_reformulation import reformulate_query
from step_01_voyage_key import find_winning_voyage_keys
from step_02_chunk_retrieval import retrieve_chunks, hybrid_retrieve_chunks
from step_03_rerank import rerank_chunks, DEFAULT_RERANK_OVERSAMPLE
from filter_args import resolve_source_types, resolve_strategies, DEFAULT_STRATEGIES


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("retrieve")

    p = argparse.ArgumentParser(description="Two-step retrieval from chunks")
    p.add_argument("--query", required=True, help="Natural language query")
    p.add_argument("--top-k-1", type=int, default=500, dest="top_k_1",
                   help="Candidates for voyage_key selection (default: 500)")
    p.add_argument("--top-k-2", type=int, default=20, dest="top_k_2",
                   help="Final chunk count (default: 20)")
    p.add_argument("--source-type", action="append", dest="source_types", metavar="TYPE",
                   help="Filter by source type: email, attachment, all (repeatable; default: email + attachment)")
    p.add_argument("--strategy", action="append", dest="strategies", metavar="STRATEGY",
                   help="Filter by embedding strategy: plain, late, context, summary, all (repeatable; default: late)")
    p.add_argument("--no-voyage-key", action="store_true", dest="no_voyage_key",
                   help="Skip step 1 (voyage_key voting); retrieve chunks across the whole index")
    p.add_argument("--embed-url", default=DEFAULT_BASE_URL,
                   help=f"Embed server base URL (default: {DEFAULT_BASE_URL})")
    p.add_argument("--reformulate", action="store_true",
                   help="Reformulate query with LLM before embedding")
    p.add_argument("--hybrid", action="store_true",
                   help="Hybrid step 2: fuse vector + BM25 via RRF (BM25 against strategy='context' only)")
    p.add_argument("--bm25-only", action="store_true", dest="bm25_only",
                   help="Step 2 uses BM25 only (diagnostic). Implies hybrid retriever path.")
    p.add_argument("--rrf-k", type=int, default=60, dest="rrf_k",
                   help="RRF constant for hybrid fusion (default: 60)")
    p.add_argument("--rerank", action="store_true",
                   help="Rerank step_02 output with Qwen3-Reranker-8B")
    p.add_argument("--rerank-pool", type=int, default=None, dest="rerank_pool",
                   help=f"Candidate pool fed to reranker (default: {DEFAULT_RERANK_OVERSAMPLE}x top-k-2)")
    p.add_argument("--rerank-url", default=DEFAULT_RERANK_URL, dest="rerank_url",
                   help=f"Reranker server base URL (default: {DEFAULT_RERANK_URL})")
    p.add_argument("--ef-search-1", type=int, default=None, dest="ef_search_1",
                   help="HNSW ef_search for step 1 (default: = top-k-1). Must be >= top-k-1.")
    p.add_argument("--ef-search-2", type=int, default=None, dest="ef_search_2",
                   help="HNSW ef_search for step 2 (default: = effective step-2 LIMIT). "
                        "Must be >= that LIMIT (= rerank-pool when --rerank, else top-k-2).")
    args = p.parse_args()

    source_types = resolve_source_types(args.source_types)
    strategies = resolve_strategies(args.strategies)

    retrieval_query = args.query
    if args.reformulate:
        retrieval_query = reformulate_query(LLMClient(), args.query)

    logger.info(f"Embedding query: {retrieval_query!r}")
    client = EmbedClient(base_url=args.embed_url)
    embedding = client.embed([retrieval_query])[0]

    t_total = time.monotonic()

    with connect() as conn:
        if args.no_voyage_key:
            winning_keys: list[str] = []
            vote_counts: dict[str, int] = {}
            step1_ms = 0
            logger.info("[step1] skipped (--no-voyage-key)")
        else:
            t1 = time.monotonic()
            winning_keys, vote_counts = find_winning_voyage_keys(
                conn, embedding, top_k=args.top_k_1,
                source_types=source_types, strategies=strategies,
                ef_search=args.ef_search_1,
            )
            step1_ms = int((time.monotonic() - t1) * 1000)

            if not winning_keys:
                logger.error("No chunks found — is the chunks table populated?")
                return

            top_vote = vote_counts[winning_keys[0]]
            logger.info(
                f"[step1] Winner(s): {winning_keys} — {top_vote}/{args.top_k_1} votes — {step1_ms}ms"
            )

        # Step 2: retrieve chunks scoped to winning key(s) (or unfiltered if skipped).
        # When --rerank is on, oversample to rerank_pool then trim to top_k_2 via reranker.
        rerank_pool = (
            args.rerank_pool
            if args.rerank_pool is not None
            else DEFAULT_RERANK_OVERSAMPLE * args.top_k_2
        )
        step2_top_k = rerank_pool if args.rerank else args.top_k_2

        t2 = time.monotonic()
        use_hybrid = args.hybrid or args.bm25_only
        if use_hybrid:
            mode = "bm25_only" if args.bm25_only else "hybrid"
            chunks = hybrid_retrieve_chunks(
                conn,
                query_text=args.query,
                query_embedding=embedding,
                voyage_keys=winning_keys if winning_keys else None,
                top_k=step2_top_k,
                source_types=source_types,
                strategies=strategies,
                rrf_k=args.rrf_k,
                mode=mode,
                ef_search=args.ef_search_2,
            )
        else:
            chunks = retrieve_chunks(
                conn, embedding,
                voyage_keys=winning_keys if winning_keys else None,
                top_k=step2_top_k,
                source_types=source_types,
                strategies=strategies,
                ef_search=args.ef_search_2,
            )
        step2_ms = int((time.monotonic() - t2) * 1000)

        logger.info(f"[step2] Retrieved {len(chunks)} chunks — {step2_ms}ms")

        rerank_ms: int | None = None
        rerank_model: str | None = None
        if args.rerank:
            rerank_client = RerankClient(base_url=args.rerank_url)
            rerank_model = rerank_client.model
            t_r = time.monotonic()
            chunks = rerank_chunks(rerank_client, args.query, chunks, top_k=args.top_k_2)
            rerank_ms = int((time.monotonic() - t_r) * 1000)
            logger.info(
                f"[rerank] {rerank_model} reduced {step2_top_k}→{len(chunks)} — {rerank_ms}ms"
            )

        if not chunks:
            logger.error("No chunks returned — check filters / index state")
            return

        total_ms = int((time.monotonic() - t_total) * 1000)
        logger.info(f"[total] {total_ms}ms")

        query_id = log_query(conn, args.query, source="terminal", username="developer")

        log_retrieval(
            conn,
            query_id=query_id,
            query_text=args.query,
            source_types=source_types if source_types is not None else ["all"],
            strategy=strategies if strategies is not None else DEFAULT_STRATEGIES,
            top_k_1=args.top_k_1,
            top_k_2=args.top_k_2,
            winning_keys=winning_keys,
            key_vote_counts=vote_counts,
            step1_ms=step1_ms,
            step2_ms=step2_ms,
            total_ms=total_ms,
            chunks_returned=len(chunks),
            chunks=chunks,
            chunks_expanded_returned=0,
            chunks_expanded=None,
            reranked=args.rerank,
            rerank_model=rerank_model,
            rerank_pool=rerank_pool if args.rerank else None,
            rerank_ms=rerank_ms,
            ef_search_1=(
                None if args.no_voyage_key
                else (args.ef_search_1 if args.ef_search_1 is not None else args.top_k_1)
            ),
            ef_search_2=(
                args.ef_search_2 if args.ef_search_2 is not None else step2_top_k
            ),
        )

    for chunk in chunks:
        print(json.dumps(
            {
                "chunk_id": chunk.chunk_id,
                "voyage_key": chunk.voyage_key,
                "source_type": chunk.source_type,
                "source_id": chunk.source_id,
                "strategy": chunk.strategy,
                "chunk_index": chunk.chunk_index,
                "similarity": round(chunk.similarity, 4),
                "text": chunk.text,
            },
            ensure_ascii=False,
        ))


if __name__ == "__main__":
    main()
