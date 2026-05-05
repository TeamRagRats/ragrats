"""
Voyage key retrieval recall test.

For every ground_truth_v2 row, embeds the question, runs find_winning_voyage_keys,
and logs the result to test_voyage_key_logging and test_retrieval_run_logging.
Results are logged separately per category (logistics_cargo / commercial_terms / incident_decision).

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
from step_01_voyage_key import find_winning_voyage_keys
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
) -> tuple[int, int]:
    hits = 0
    for i, (question_id, question, expected_key) in enumerate(rows, 1):
        embedding = client.embed([question])[0]
        winning_keys, vote_counts = find_winning_voyage_keys(conn, embedding, top_k=top_k)

        hit = expected_key in vote_counts
        rank = _compute_rank(expected_key, vote_counts)
        if hit:
            hits += 1

        log_voyage_key_testing(
            conn,
            run_id=run_id,
            question_id=question_id,
            top_k=top_k,
            expected_key=expected_key,
            returned_keys=winning_keys,
            hit=hit,
            winner_rank=rank,
            vote_counts=vote_counts,
        )

        if i % 50 == 0:
            print(f"  [{question_type}] {i}/{len(rows)} — recall: {hits}/{i} ({hits/i:.1%})")

    return hits, len(rows)


def main() -> None:
    p = argparse.ArgumentParser(description="Voyage key retrieval recall test")
    p.add_argument("--top-k", type=int, default=500, dest="top_k",
                   help="Candidates for voyage_key voting (default: 500)")
    p.add_argument("--embed-url", default=DEFAULT_BASE_URL,
                   help=f"Embed server base URL (default: {DEFAULT_BASE_URL})")
    args = p.parse_args()

    with connect() as conn:
        all_rows = conn.execute("""
            SELECT question_id, question, voyage_key, category
            FROM ground_truth_v2
            ORDER BY category, question_id
        """).fetchall()

    rows_by_category: dict[str, list] = {}
    for question_id, question, voyage_key, category in all_rows:
        rows_by_category.setdefault(category, []).append((question_id, question, voyage_key))

    summary = " | ".join(f"{cat}: {len(rows)}" for cat, rows in sorted(rows_by_category.items()))
    print(f"{summary} | top_k: {args.top_k}")

    client = EmbedClient(base_url=args.embed_url)
    run_id = str(uuid.uuid4())

    results: dict[str, tuple[int, int]] = {}
    with connect() as conn:
        for category, rows in sorted(rows_by_category.items()):
            hits, total = _run_for_type(conn, client, rows, run_id, args.top_k, category)
            results[category] = (hits, total)

    with connect() as conn:
        for category, (hits, total) in results.items():
            recall = hits / total if total else 0.0
            log_retrieval_run(
                conn,
                run_id=run_id,
                test_type="voyage_key_retrieval",
                question_type=category,
                top_k=args.top_k,
                total=total,
                hits=hits,
                recall=recall,
            )

    print(f"\nDone. run_id={run_id}")
    for category, (hits, total) in sorted(results.items()):
        recall = hits / total if total else 0.0
        print(f"{category} ({total}): recall@{args.top_k}: {hits}/{total} ({recall:.1%})")


if __name__ == "__main__":
    main()
