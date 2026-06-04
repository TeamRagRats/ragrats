"""
Voyage key retrieval recall test.

For every ground_truth row, embeds the question, runs find_winning_voyage_keys,
and logs the result to test_retrieval_vk_logging and test_retrieval_run_logging.
Unanswerable questions are skipped. Results are logged per answerable category
(fact_single / summary / reasoning) plus an aggregate 'total' row.

Run on SPARK where both postgres and the embed server are reachable:
    python run_test.py
    python run_test.py --top-k 200
    python run_test.py --embed-url http://localhost:8003/v1
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _repo_root = _here.parents[3]
    _retrieval = _repo_root / "src" / "02_retrieval"
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_retrieval))
    __package__ = "src.testing.retrieval.voyage_key"

import argparse
import uuid

from core.db import connect
from clients.embed_client import EmbedClient, DEFAULT_BASE_URL
from clients.llm_client import LLMClient
from step_00_query_reformulation import reformulate_query
from step_01_voyage_key import find_winning_voyage_keys
from filter_args import resolve_source_types, resolve_strategies, resolve_chunkers
from log.log_voyage_key_testing import log_voyage_key_testing
from log.log_testing import log_retrieval_run


def _compute_rank(expected_key: str, vote_counts: dict[str, int]) -> int | None:
    if expected_key not in vote_counts:
        return None
    sorted_keys = sorted(vote_counts, key=lambda k: -vote_counts[k])
    return sorted_keys.index(expected_key) + 1


def _run_for_type(
    conn,
    client,
    rows: list,
    run_id: str,
    top_k: int,
    question_type: str,
    rank_threshold: int | None,
    source_types: list[str] | None,
    strategies: list[str] | None,
    chunkers: list[str] | None,
    flags: dict,
    llm: LLMClient | None = None,
    ef_search: int | None = None,
) -> tuple[int, int]:
    hits = 0
    for i, (question_id, question, expected_key) in enumerate(rows, 1):
        q = reformulate_query(llm, question) if llm else question
        embedding = client.embed([q])[0]
        winning_keys, vote_counts, candidates = find_winning_voyage_keys(
            conn, embedding, top_k=top_k,
            source_types=source_types, strategies=strategies, chunkers=chunkers,
            ef_search=ef_search, return_candidates=True,
        )

        rank = _compute_rank(expected_key, vote_counts)
        if rank_threshold is None:
            hit = expected_key in vote_counts
        else:
            hit = rank is not None and rank <= rank_threshold
        if hit:
            hits += 1

        log_voyage_key_testing(
            conn,
            run_id=run_id,
            question_id=question_id,
            category=question_type,
            question=question,
            expected_key=expected_key,
            returned_keys=winning_keys,
            hit=hit,
            winner_rank=rank,
            vote_counts=vote_counts,
            chunks=candidates,
            flags=flags,
        )

        if i % 50 == 0:
            print(f"  [{question_type}] {i}/{len(rows)} — recall: {hits}/{i} ({hits/i:.1%})")

    return hits, len(rows)


def main() -> None:
    p = argparse.ArgumentParser(description="Voyage key retrieval recall test")
    p.add_argument("--top-k", type=int, default=5, dest="top_k",
                   help="Candidates for voyage_key voting (default: 500)")
    p.add_argument("--embed-url", default=DEFAULT_BASE_URL,
                   help=f"Embed server base URL (default: {DEFAULT_BASE_URL})")
    p.add_argument("--source-type", action="append", dest="source_types", metavar="TYPE",
                   help="Filter by source type: email, attachment, all (repeatable; default: email + attachment)")
    p.add_argument("--strategy", action="append", dest="strategies", metavar="STRATEGY",
                   help="Filter by embedding strategy: plain, late, context, summary, all (repeatable; default: plain)")
    p.add_argument("--chunker", action="append", dest="chunkers", metavar="CHUNKER",
                   help="Filter by chunk collection label: e.g. 1500, 1000, naive, all "
                        "(repeatable; default: 1500). 'all' blends every size.")
    p.add_argument("--rank-threshold", type=int, default=None, dest="rank_threshold",
                   help="Stricter hit definition: expected_key must be in the top-N "
                        "by vote count among the top_k chunks (e.g. --rank-threshold 3). "
                        "Default: no threshold = true recall@k.")
    p.add_argument("--voyage", type=str, default=None,
                   help="Run only on this voyage_key (default: all voyages in ground_truth)")
    p.add_argument("--reformulate", action="store_true",
                   help="Reformulate questions with LLM before embedding")
    p.add_argument("--ef-search", type=int, default=None, dest="ef_search",
                   help="HNSW ef_search for step 1 (default: = top-k). Must be >= top-k.")
    args = p.parse_args()

    source_types = resolve_source_types(args.source_types)
    strategies = resolve_strategies(args.strategies)
    chunkers = resolve_chunkers(args.chunkers)

    voyage_filter_sql = "WHERE voyage_key = %(voyage)s" if args.voyage else ""
    voyage_params = {"voyage": args.voyage} if args.voyage else {}
    with connect() as conn:
        all_rows = conn.execute(f"""
            SELECT question_id::text, question, voyage_key, category
            FROM ground_truth
            {voyage_filter_sql}
            ORDER BY category, question_id::text
        """, voyage_params).fetchall()

    rows_by_category: dict[str, list] = {}
    for question_id, question, voyage_key, category in all_rows:
        if category == "unanswerable":
            continue
        rows_by_category.setdefault(category, []).append((question_id, question, voyage_key))

    summary = " | ".join(f"{cat}: {len(rows)}" for cat, rows in sorted(rows_by_category.items()))
    threshold_str = f" | rank<= {args.rank_threshold}" if args.rank_threshold else ""
    ef = args.ef_search if args.ef_search is not None else args.top_k
    strategy_str = ",".join(strategies) if strategies else "all"
    print(f"{summary} | top_k: {args.top_k} | ef_search: {ef} | strategy: {strategy_str}{threshold_str}")

    flags = {
        "top_k": args.top_k,
        "ef_search": ef,
        "strategy": strategies if strategies is not None else "all",
        "chunker": chunkers if chunkers is not None else "all",
        "source_types": source_types if source_types is not None else "all",
        "rank_threshold": args.rank_threshold,
        "reformulator": args.reformulate,
    }

    client = EmbedClient(base_url=args.embed_url)
    llm = LLMClient() if args.reformulate else None
    run_id = str(uuid.uuid4())

    results: dict[str, tuple[int, int]] = {}
    with connect() as conn:
        for category, rows in sorted(rows_by_category.items()):
            hits, total = _run_for_type(
                conn, client, rows, run_id, args.top_k, category, args.rank_threshold,
                source_types=source_types, strategies=strategies, chunkers=chunkers,
                flags=flags,
                llm=llm,
                ef_search=args.ef_search,
            )
            results[category] = (hits, total)

    total_hits = sum(hits for hits, _ in results.values())
    total_questions = sum(total for _, total in results.values())

    with connect() as conn:
        for category, (hits, total) in results.items():
            recall = hits / total if total else 0.0
            log_retrieval_run(
                conn,
                run_id=run_id,
                test_type="voyage_key_retrieval",
                question_type=category,
                total=total,
                thread_hits=hits,
                thread_recall=recall,
                flags=flags,
            )

        total_recall = total_hits / total_questions if total_questions else 0.0
        log_retrieval_run(
            conn,
            run_id=run_id,
            test_type="voyage_key_retrieval",
            question_type="total",
            total=total_questions,
            thread_hits=total_hits,
            thread_recall=total_recall,
            flags=flags,
        )

    print(f"\nDone. run_id={run_id} | strategy: {strategy_str}")
    metric_label = (f"recall@{args.top_k} (rank<= {args.rank_threshold})"
                    if args.rank_threshold else f"recall@{args.top_k}")
    for category, (hits, total) in sorted(results.items()):
        recall = hits / total if total else 0.0
        print(f"{category} ({total}): {metric_label}: {hits}/{total} ({recall:.1%})")
    total_recall = total_hits / total_questions if total_questions else 0.0
    print(f"total ({total_questions}): {metric_label}: {total_hits}/{total_questions} ({total_recall:.1%})")


if __name__ == "__main__":
    main()
