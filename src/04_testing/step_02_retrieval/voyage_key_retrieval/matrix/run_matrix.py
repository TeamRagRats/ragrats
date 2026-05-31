"""Voyage-key recall matrix: strategy × k × category.

Fixed flags (source-type, optional reformulation) are held constant; we iterate
over embedding strategies and over a k scale (1..20 one at a time, then +10 up to
500 — ~68 k values). For each (strategy, k) we log recall per answerable category
(fact_single / summary / reasoning) plus an aggregated 'total' row to
test_retrieval_run_logging. Unanswerable is not run.

Efficiency: each question is embedded once, and per (question, strategy) the
top-`pool` candidates are fetched once (ef_search=pool); recall@k is computed by
slicing the list instead of running an HNSW search per k.

Run on SPARK where both postgres and the embed server are available:
    python run_matrix.py
    python run_matrix.py --strategy late --strategy plain
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _repo_root = _here.parents[4]
    _retrieval = _repo_root / "src" / "02_retrieval"
    sys.path.insert(0, str(_here))
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_retrieval))

import argparse
import uuid

from core.db import connect
from clients.embed_client import EmbedClient, DEFAULT_BASE_URL
from clients.llm_client import LLMClient
from step_00_query_reformulation import reformulate_query
from filter_args import resolve_source_types, resolve_strategies
from log.log_testing import log_retrieval_run

from k_schedule import build_k_values
from pool_query import ranked_voyage_keys, hit_at_k

EMBED_BATCH = 64


def _embed_questions(client, rows, llm) -> dict[str, list[float]]:
    """Embed each question once (independent of strategy and k)."""
    cache: dict[str, list[float]] = {}
    pending_ids: list[str] = []
    pending_text: list[str] = []
    for question_id, question, _expected, _category in rows:
        if question_id in cache or question_id in pending_ids:
            continue
        q = reformulate_query(llm, question) if llm else question
        pending_ids.append(question_id)
        pending_text.append(q)

    for start in range(0, len(pending_text), EMBED_BATCH):
        batch_ids = pending_ids[start:start + EMBED_BATCH]
        batch_text = pending_text[start:start + EMBED_BATCH]
        for qid, emb in zip(batch_ids, client.embed(batch_text)):
            cache[qid] = emb
    return cache


def _collect_for_strategy(conn, rows, cache, pool, source_types, strategy):
    """{category: [(expected_key, ranked_keys), ...]} for one strategy."""
    by_cat: dict[str, list[tuple[str, list[str]]]] = {}
    for i, (question_id, _question, expected_key, category) in enumerate(rows, 1):
        ranked = ranked_voyage_keys(conn, cache[question_id], pool, source_types, strategy)
        by_cat.setdefault(category, []).append((expected_key, ranked))
        if i % 100 == 0:
            print(f"    [{strategy}] pool {i}/{len(rows)}")
    return by_cat


def _log_strategy(conn, by_cat, k_values, pool, source_types, strategy,
                  reformulate, rank_threshold, matrix_id):
    for k in k_values:
        run_id = str(uuid.uuid4())
        flags = {
            "matrix_id": matrix_id,
            "strategy": [strategy],
            "top_k": k,
            "ef_search": pool,
            "pool": pool,
            "source_types": source_types if source_types is not None else "all",
            "rank_threshold": rank_threshold,
            "reformulator": reformulate,
        }
        total_hits = 0
        total_q = 0
        for category, items in sorted(by_cat.items()):
            hits = sum(1 for expected_key, ranked in items
                       if hit_at_k(ranked, expected_key, k, rank_threshold))
            total = len(items)
            log_retrieval_run(
                conn, run_id=run_id, test_type="voyage_key_retrieval",
                question_type=category, total=total,
                thread_hits=hits, thread_recall=hits / total if total else 0.0,
                flags=flags,
            )
            total_hits += hits
            total_q += total
        log_retrieval_run(
            conn, run_id=run_id, test_type="voyage_key_retrieval",
            question_type="total", total=total_q,
            thread_hits=total_hits, thread_recall=total_hits / total_q if total_q else 0.0,
            flags=flags,
        )


def main() -> None:
    p = argparse.ArgumentParser(description="Voyage-key recall matrix (strategy × k × category)")
    p.add_argument("--embed-url", default=DEFAULT_BASE_URL,
                   help=f"Embed server base URL (default: {DEFAULT_BASE_URL})")
    p.add_argument("--source-type", action="append", dest="source_types", metavar="TYPE",
                   help="Filter by source type: email, attachment, all (default: email + attachment)")
    p.add_argument("--strategy", action="append", dest="strategies", metavar="STRATEGY",
                   help="Strategies to iterate over (repeatable; default: plain, late, context, summary)")
    p.add_argument("--pool", type=int, default=500,
                   help="Candidate pool / max k (default: 500). Must be >= the largest k.")
    p.add_argument("--voyage", type=str, default=None,
                   help="Run only on this voyage_key (default: all in ground_truth)")
    p.add_argument("--reformulate", action="store_true",
                   help="Reformulate questions with the LLM before embedding")
    p.add_argument("--rank-threshold", type=int, default=None, dest="rank_threshold",
                   help="Test the voting: hit only if expected_key is among the N "
                        "most-voted keys in top-k (e.g. --rank-threshold 1 = the "
                        "winning key). Default: none = plain recall@k.")
    args = p.parse_args()

    source_types = resolve_source_types(args.source_types)
    if args.strategies:
        strategies = resolve_strategies(args.strategies)
        if strategies is None:
            strategies = ["plain", "late", "context", "summary"]
    else:
        strategies = ["plain", "late", "context", "summary"]

    k_values = build_k_values(coarse_max=args.pool)
    if max(k_values) > args.pool:
        raise SystemExit(f"--pool ({args.pool}) must be >= the largest k ({max(k_values)})")

    voyage_filter_sql = "WHERE voyage_key = %(voyage)s" if args.voyage else ""
    voyage_params = {"voyage": args.voyage} if args.voyage else {}
    with connect() as conn:
        all_rows = conn.execute(f"""
            SELECT question_id::text, question, voyage_key, category
            FROM ground_truth
            {voyage_filter_sql}
            ORDER BY category, question_id::text
        """, voyage_params).fetchall()

    rows = [r for r in all_rows if r[3] != "unanswerable"]
    cat_counts: dict[str, int] = {}
    for _qid, _q, _vk, category in rows:
        cat_counts[category] = cat_counts.get(category, 0) + 1

    matrix_id = str(uuid.uuid4())
    print(f"matrix_id={matrix_id}")
    print(f"categories: " + " | ".join(f"{c}: {n}" for c, n in sorted(cat_counts.items())))
    metric = f"rank<= {args.rank_threshold} (voting)" if args.rank_threshold else "recall@k"
    print(f"strategies: {strategies} | k values: {len(k_values)} (1..{max(k_values)}) | pool: {args.pool} | metric: {metric}")
    print(f"runs total: {len(strategies)} × {len(k_values)} = {len(strategies) * len(k_values)} per category")

    client = EmbedClient(base_url=args.embed_url)
    llm = LLMClient() if args.reformulate else None

    print("Embedding questions (once)...")
    cache = _embed_questions(client, rows, llm)

    for strategy in strategies:
        print(f"Strategy: {strategy}")
        with connect() as conn:
            by_cat = _collect_for_strategy(conn, rows, cache, args.pool, source_types, strategy)
            _log_strategy(conn, by_cat, k_values, args.pool, source_types,
                          strategy, args.reformulate, args.rank_threshold, matrix_id)

    print(f"\nDone. matrix_id={matrix_id}")


if __name__ == "__main__":
    main()
