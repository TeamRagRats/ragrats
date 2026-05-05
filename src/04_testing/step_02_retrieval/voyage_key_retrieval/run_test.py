"""
Voyage key retrieval recall test.

For every ground_truth row, embeds the question, runs find_winning_voyage_keys,
and logs the result to test_voyage_key_logging and test_retrieval_run_logging.
Results are logged separately per question_type (extractive / investigative).

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

        hit = expected_key in winning_keys
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
        extractive_rows = conn.execute("""
            SELECT question_id, question, voyage_key
            FROM ground_truth
            WHERE question_type = 'extractive'
            ORDER BY question_id
        """).fetchall()

        investigative_rows = conn.execute("""
            SELECT question_id, question, voyage_key
            FROM ground_truth
            WHERE question_type = 'investigative'
            ORDER BY question_id
        """).fetchall()

    print(f"Extractive: {len(extractive_rows)} | Investigative: {len(investigative_rows)} | top_k: {args.top_k}")

    client = EmbedClient(base_url=args.embed_url)
    run_id = str(uuid.uuid4())

    with connect() as conn:
        ext_hits, ext_total = _run_for_type(conn, client, extractive_rows, run_id, args.top_k, "extractive")
        inv_hits, inv_total = _run_for_type(conn, client, investigative_rows, run_id, args.top_k, "investigative")

    ext_recall = ext_hits / ext_total if ext_total else 0.0
    inv_recall = inv_hits / inv_total if inv_total else 0.0

    with connect() as conn:
        log_retrieval_run(
            conn,
            run_id=run_id,
            test_type="voyage_key_retrieval",
            question_type="extractive",
            top_k=args.top_k,
            total=ext_total,
            hits=ext_hits,
            recall=ext_recall,
        )
        log_retrieval_run(
            conn,
            run_id=run_id,
            test_type="voyage_key_retrieval",
            question_type="investigative",
            top_k=args.top_k,
            total=inv_total,
            hits=inv_hits,
            recall=inv_recall,
        )

    print(f"\nDone. run_id={run_id}")
    print(f"Extractive   ({ext_total}): recall@{args.top_k}: {ext_hits}/{ext_total} ({ext_recall:.1%})")
    print(f"Investigative ({inv_total}): recall@{args.top_k}: {inv_hits}/{inv_total} ({inv_recall:.1%})")


if __name__ == "__main__":
    main()
