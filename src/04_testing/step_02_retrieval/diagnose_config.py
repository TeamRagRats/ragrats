"""
One-shot diagnostic for the retrieval pipeline.

Prints the ACTUAL configuration produced by the production code paths, so
stale documentation and silent default mismatches become visible in a single
run. Specifically:

  1. Which model the reranker container actually serves (via GET /v1/models).
     Reveals if docs / README still claim e.g. "Qwen3-Reranker-8B" while the
     container serves 4B.

  2. Effective pool sizes when --hybrid --rerank are combined: the hybrid
     retriever oversamples vector+BM25 to 2*top_k internally, while ef_search
     defaults to step2_top_k = rerank_pool. If ef_search < vector_pool,
     pgvector silently degrades recall.

  3. Default DEFAULT_STRATEGIES vs the help-text claim (sanity check after the
     test-fix branch cleanup).

Read-only: never touches the DB and never embeds. Safe to run anywhere.

Examples:
    python diagnose_config.py
    python diagnose_config.py --top-k-2 20 --rerank-pool 60
    python diagnose_config.py --rerank-url http://localhost:8004/v1
"""
from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _repo_root = _here.parents[2]
    _retrieval = _repo_root / "src" / "02_retrieval"
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_retrieval))

import argparse
import json
import urllib.error
import urllib.request

from clients.rerank_client import DEFAULT_BASE_URL as DEFAULT_RERANK_URL
from filter_args import DEFAULT_STRATEGIES
from step_03_rerank import DEFAULT_RERANK_OVERSAMPLE


def _fetch_model_id(rerank_url: str) -> str | None:
    try:
        req = urllib.request.Request(f"{rerank_url.rstrip('/')}/models")
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        data = payload.get("data") or []
        return data[0]["id"] if data else None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def main() -> None:
    p = argparse.ArgumentParser(description="Pipeline config diagnostic")
    p.add_argument("--top-k-2", type=int, default=20, dest="top_k_2",
                   help="Final chunk count (mirrors run_retrieve / run_test defaults)")
    p.add_argument("--rerank-pool", type=int, default=None, dest="rerank_pool",
                   help=f"Reranker candidate pool (default: {DEFAULT_RERANK_OVERSAMPLE}x top-k-2)")
    p.add_argument("--ef-search-2", type=int, default=None, dest="ef_search_2",
                   help="HNSW ef_search for step 2 (default: = effective step-2 LIMIT)")
    p.add_argument("--rerank-url", default=DEFAULT_RERANK_URL,
                   help=f"Reranker base URL (default: {DEFAULT_RERANK_URL})")
    args = p.parse_args()

    rerank_pool = args.rerank_pool if args.rerank_pool is not None \
        else DEFAULT_RERANK_OVERSAMPLE * args.top_k_2
    step2_top_k_when_rerank = rerank_pool
    vector_pool_inside_hybrid = 2 * step2_top_k_when_rerank
    bm25_pool_inside_hybrid = 2 * step2_top_k_when_rerank
    ef_search_default = args.ef_search_2 if args.ef_search_2 is not None \
        else step2_top_k_when_rerank

    print("=" * 70)
    print("RETRIEVAL PIPELINE CONFIG DIAGNOSTIC")
    print("=" * 70)

    print(f"\n[1] Default embedding strategies: {DEFAULT_STRATEGIES}")
    print("    Test runners default to this when --strategy is omitted.")

    print(f"\n[2] Reranker server @ {args.rerank_url}")
    model_id = _fetch_model_id(args.rerank_url)
    if model_id is None:
        print("    UNREACHABLE — server not running or wrong URL.")
    else:
        print(f"    Deployed model: {model_id}")
        if "8B" in model_id:
            print("    Doc claims:   Qwen3-Reranker-8B  → MATCHES.")
        elif "4B" in model_id:
            print("    Doc claims:   Qwen3-Reranker-8B  → STALE (deployed is 4B).")
        else:
            print("    Doc claims:   Qwen3-Reranker-8B  → DIVERGES.")

    print(f"\n[3] Effective config @ --hybrid --rerank --top-k-2 {args.top_k_2}:")
    print(f"    rerank_pool                 = {rerank_pool}  "
          f"(= DEFAULT_RERANK_OVERSAMPLE={DEFAULT_RERANK_OVERSAMPLE} × top_k_2)")
    print(f"    step_02 LIMIT (vector/BM25) = {step2_top_k_when_rerank}  "
          f"(forwarded to hybrid_retrieve_chunks)")
    print(f"    vector_pool inside hybrid   = {vector_pool_inside_hybrid}  "
          f"(= 2 × step_02 LIMIT, set in retrieve_hybrid.py)")
    print(f"    bm25_pool inside hybrid     = {bm25_pool_inside_hybrid}")
    print(f"    ef_search_2 (HNSW)          = {ef_search_default}")

    if ef_search_default < vector_pool_inside_hybrid:
        print(
            f"\n    WARNING: ef_search ({ef_search_default}) < vector_pool "
            f"({vector_pool_inside_hybrid})."
        )
        print("    pgvector requires ef_search >= LIMIT for full HNSW recall.")
        print(f"    Pass --ef-search-2 {vector_pool_inside_hybrid} (or higher) to fix.")
    else:
        print(f"\n    ef_search >= vector_pool — OK.")

    sota_recommended = 10 * args.top_k_2
    if rerank_pool < sota_recommended:
        print(
            f"\n[4] Rerank pool ({rerank_pool}) is below SOTA cross-encoder guidance "
            f"({sota_recommended} = 10× top-k-2)."
        )
        print("    Strong cross-encoders typically benefit from 5-10x oversample.")
        print("    Consider --rerank-pool 100-200 for benchmarking.")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
