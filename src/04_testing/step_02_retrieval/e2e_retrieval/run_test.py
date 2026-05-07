"""
End-to-end retrieval recall test — full pipeline (step 1 → step 2 → expand).

For every ground_truth_v2 row, embeds the question, runs the production
pipeline (find_winning_voyage_keys → retrieve_chunks → expand_chunks) and
checks two things:
  - voyage key recall:  expected_key in winning_keys (vote winners)
  - chunk recall:       expected_chunk_id in expanded chunks

Results are split per category (logistics_cargo / commercial_terms /
incident_decision). Voyage key and chunk results are logged separately to
test_retrieval_run_logging under the same run_id so they can be compared
side by side, and per-question chunk results to test_chunk_retrieval_logging.

Run on SPARK where both postgres and the embed server are reachable:
    python run_test.py
    python run_test.py --top-k-1 500 --top-k-2 20
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
    __package__ = "src.testing.retrieval.e2e"

import argparse
import uuid

from core.db import connect
from clients.embed_client import EmbedClient, DEFAULT_BASE_URL
from step_01_voyage_key import find_winning_voyage_keys
from step_02_chunk_retrieval.retrieve_chunks import retrieve_chunks
from step_02_chunk_retrieval.expand_chunks import expand_chunks
from log.log_chunk_retrieval_testing import log_chunk_retrieval_testing
from log.log_testing import log_retrieval_run


def _compute_chunk_rank(expected_chunk_id: str, chunks: list) -> int | None:
    for i, chunk in enumerate(chunks, 1):
        if chunk.chunk_id == expected_chunk_id:
            return i
    return None


def _run_for_category(
    conn,
    client: EmbedClient,
    rows: list,
    run_id: str,
    top_k_1: int,
    top_k_2: int,
    expand_window: int,
    category: str,
) -> tuple[int, int, int, float]:
    key_hits = 0
    chunk_hits = 0
    mrr_sum = 0.0
    total = len(rows)

    for i, (question_id, question, expected_key, expected_chunk_id) in enumerate(rows, 1):
        embedding = client.embed([question])[0]

        winning_keys, vote_counts = find_winning_voyage_keys(conn, embedding, top_k=top_k_1)
        if expected_key in vote_counts:
            key_hits += 1

        anchor_chunks = retrieve_chunks(conn, embedding, voyage_keys=winning_keys, top_k=top_k_2)
        expanded_chunks = expand_chunks(conn, anchor_chunks, window=expand_window)

        expanded_chunk_ids = [c.chunk_id for c in expanded_chunks]
        rank = _compute_chunk_rank(expected_chunk_id, anchor_chunks)
        hit = expected_chunk_id in expanded_chunk_ids

        if hit:
            chunk_hits += 1
        if rank is not None:
            mrr_sum += 1.0 / rank

        log_chunk_retrieval_testing(
            conn,
            run_id=run_id,
            question_id=question_id,
            top_k=top_k_2,
            expected_source_id=expected_chunk_id,
            returned_source_ids=expanded_chunk_ids,
            hit=hit,
            source_rank=rank,
        )

        if i % 50 == 0:
            print(
                f"  [{category}] {i}/{total} — "
                f"key: {key_hits/i:.1%} | chunk: {chunk_hits/i:.1%}"
            )

    mrr = mrr_sum / total if total else 0.0
    return key_hits, chunk_hits, total, mrr


def main() -> None:
    p = argparse.ArgumentParser(description="End-to-end retrieval recall test")
    p.add_argument("--top-k-1", type=int, default=500, dest="top_k_1",
                   help="Candidates for voyage_key voting (default: 500)")
    p.add_argument("--top-k-2", type=int, default=20, dest="top_k_2",
                   help="Chunks to retrieve per question (default: 20)")
    p.add_argument("--expand-window", type=int, default=2, dest="expand_window",
                   help="Neighbor chunks on each side of an anchor (default: 2)")
    p.add_argument("--embed-url", default=DEFAULT_BASE_URL,
                   help=f"Embed server base URL (default: {DEFAULT_BASE_URL})")
    args = p.parse_args()

    with connect() as conn:
        all_rows = conn.execute("""
            SELECT question_id, question, voyage_key, source_chunk_id::text, category
            FROM ground_truth_v2
            ORDER BY category, question_id
        """).fetchall()

    rows_by_category: dict[str, list] = {}
    for question_id, question, voyage_key, source_chunk_id, category in all_rows:
        rows_by_category.setdefault(category, []).append(
            (question_id, question, voyage_key, source_chunk_id)
        )

    summary = " | ".join(f"{cat}: {len(rows)}" for cat, rows in sorted(rows_by_category.items()))
    print(
        f"{summary} | top_k_1: {args.top_k_1} | top_k_2: {args.top_k_2} | expand: ±{args.expand_window}"
    )

    client = EmbedClient(base_url=args.embed_url)
    run_id = str(uuid.uuid4())

    results: dict[str, tuple[int, int, int, float]] = {}
    with connect() as conn:
        for category, rows in sorted(rows_by_category.items()):
            key_hits, chunk_hits, total, mrr = _run_for_category(
                conn, client, rows, run_id,
                args.top_k_1, args.top_k_2, args.expand_window, category,
            )
            results[category] = (key_hits, chunk_hits, total, mrr)

    with connect() as conn:
        for category, (key_hits, chunk_hits, total, _) in results.items():
            key_recall = key_hits / total if total else 0.0
            chunk_recall = chunk_hits / total if total else 0.0
            log_retrieval_run(
                conn,
                run_id=run_id,
                test_type="voyage_key_retrieval_e2e",
                question_type=category,
                top_k=args.top_k_1,
                total=total,
                hits=key_hits,
                recall=key_recall,
            )
            log_retrieval_run(
                conn,
                run_id=run_id,
                test_type="chunk_retrieval_e2e",
                question_type=category,
                top_k=args.top_k_2,
                total=total,
                hits=chunk_hits,
                recall=chunk_recall,
            )

    print(f"\nDone. run_id={run_id}")
    for category, (key_hits, chunk_hits, total, mrr) in sorted(results.items()):
        key_recall = key_hits / total if total else 0.0
        chunk_recall = chunk_hits / total if total else 0.0
        print(
            f"{category} ({total}): "
            f"key recall: {key_recall:.1%} | chunk recall: {chunk_recall:.1%} | MRR: {mrr:.4f}"
        )


if __name__ == "__main__":
    main()
