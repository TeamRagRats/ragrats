"""CLI surface for chunk_retrieval/run_test.py.

argparse definitions and the derived run-config (resolved filters, hybrid
mode, rerank pool, ef_search, strategy label, flags JSON).
"""
from __future__ import annotations

import argparse

from clients.embed_client import DEFAULT_BASE_URL
from clients.rerank_client import DEFAULT_BASE_URL as DEFAULT_RERANK_URL
from step_03_rerank import DEFAULT_RERANK_OVERSAMPLE
from filter_args import resolve_source_types, resolve_strategies


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Isolated chunk retrieval test (step 2 only)")
    p.add_argument("--top-k", type=int, default=20, dest="top_k",
                   help="Chunks to retrieve per question (default: 20)")
    p.add_argument("--embed-url", default=DEFAULT_BASE_URL,
                   help=f"Embed server base URL (default: {DEFAULT_BASE_URL})")
    p.add_argument("--source-type", action="append", dest="source_types", metavar="TYPE",
                   help="Filter by source type: email, attachment, all (repeatable; default: email + attachment)")
    p.add_argument("--strategy", action="append", dest="strategies", metavar="STRATEGY",
                   help="Filter by embedding strategy: plain, late, context, summary, all (repeatable; default: plain)")
    p.add_argument("--voyage", type=str, default=None,
                   help="Run only on this voyage_key (default: all voyages in ground_truth)")
    p.add_argument("--reformulate", action="store_true",
                   help="Reformulate questions with LLM before embedding")
    p.add_argument("--hybrid", action="store_true",
                   help="Hybrid retrieval: fuse vector + BM25 via RRF (BM25 against strategy='context' only)")
    p.add_argument("--bm25-only", action="store_true", dest="bm25_only",
                   help="BM25-only retrieval (diagnostic). Implies hybrid retriever path.")
    p.add_argument("--rrf-k", type=int, default=60, dest="rrf_k",
                   help="RRF constant for hybrid fusion (default: 60)")
    p.add_argument("--rerank", action="store_true",
                   help="Rerank retrieved chunks with Qwen3-Reranker-8B")
    p.add_argument("--rerank-pool", type=int, default=None, dest="rerank_pool",
                   help=f"Candidate pool fed to reranker (default: {DEFAULT_RERANK_OVERSAMPLE}x top-k)")
    p.add_argument("--rerank-url", default=DEFAULT_RERANK_URL, dest="rerank_url",
                   help=f"Reranker server base URL (default: {DEFAULT_RERANK_URL})")
    p.add_argument("--ef-search", type=int, default=None, dest="ef_search",
                   help="HNSW ef_search for step 2 (default: = effective LIMIT). "
                        "Must be >= effective LIMIT (= rerank-pool when --rerank, else top-k).")
    return p.parse_args()


def resolve_config(args: argparse.Namespace) -> dict:
    source_types = resolve_source_types(args.source_types)
    strategies = resolve_strategies(args.strategies)
    hybrid_mode = "bm25_only" if args.bm25_only else ("hybrid" if args.hybrid else None)
    rerank_pool = (
        args.rerank_pool
        if args.rerank_pool is not None
        else DEFAULT_RERANK_OVERSAMPLE * args.top_k
    )
    ef = args.ef_search if args.ef_search is not None else args.top_k
    strategy_str = ",".join(strategies) if strategies else "all"
    flags = {
        "top_k": args.top_k,
        "ef_search": ef,
        "strategy": strategies if strategies is not None else "all",
        "source_types": source_types if source_types is not None else "all",
        "hybrid": hybrid_mode,
        "rrf_k": args.rrf_k if hybrid_mode is not None else None,
        "reranker": args.rerank,
        "rerank_pool": rerank_pool if args.rerank else None,
        "reformulator": args.reformulate,
    }
    return {
        "source_types": source_types,
        "strategies": strategies,
        "hybrid_mode": hybrid_mode,
        "rerank_pool": rerank_pool,
        "ef": ef,
        "strategy_str": strategy_str,
        "flags": flags,
    }
