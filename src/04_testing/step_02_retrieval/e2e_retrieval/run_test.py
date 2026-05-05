"""
End-to-end retrieval recall test — full pipeline (step 1 → step 2 → expand).

Extractive questions (question_type='extractive'):
  Runs the full production pipeline (step 1 → step 2 → expand) and checks
  if the expected source_chunk_id appears in the expanded set.

Investigative questions (question_type='investigative'):
  Runs step 1 only and checks if the expected voyage_key is in the
  winning keys (no single source chunk to evaluate against).

Both sets are logged separately to test_retrieval_run_logging under the
same run_id so results can be compared side by side.

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
        extractive_rows = conn.execute("""
            SELECT question_id, question, voyage_key, source_chunk_id::text
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

    print(
        f"Extractive: {len(extractive_rows)} | Investigative: {len(investigative_rows)} | "
        f"top_k_1: {args.top_k_1} | top_k_2: {args.top_k_2} | expand: ±{args.expand_window}"
    )

    client = EmbedClient(base_url=args.embed_url)
    run_id = str(uuid.uuid4())

    # --- Extractive ---
    ext_hits = 0
    ext_key_hits = 0
    ext_mrr = 0.0

    with connect() as conn:
        for i, (question_id, question, expected_key, expected_chunk_id) in enumerate(extractive_rows, 1):
            embedding = client.embed([question])[0]

            winning_keys, vote_counts = find_winning_voyage_keys(conn, embedding, top_k=args.top_k_1)
            if expected_key in winning_keys:
                ext_key_hits += 1

            anchor_chunks = retrieve_chunks(conn, embedding, voyage_keys=winning_keys, top_k=args.top_k_2)
            expanded_chunks = expand_chunks(conn, anchor_chunks, window=args.expand_window)

            expanded_chunk_ids = [c.chunk_id for c in expanded_chunks]
            rank = _compute_chunk_rank(expected_chunk_id, anchor_chunks)
            hit = expected_chunk_id in expanded_chunk_ids

            if hit:
                ext_hits += 1
            if rank is not None:
                ext_mrr += 1.0 / rank

            log_chunk_retrieval_testing(
                conn,
                run_id=run_id,
                question_id=question_id,
                top_k=args.top_k_2,
                expected_source_id=expected_chunk_id,
                returned_source_ids=expanded_chunk_ids,
                hit=hit,
                source_rank=rank,
            )

            if i % 50 == 0:
                print(f"  [extractive] {i}/{len(extractive_rows)} — key: {ext_key_hits/i:.1%} | chunk: {ext_hits/i:.1%}")

    ext_total = len(extractive_rows)
    ext_recall = ext_hits / ext_total if ext_total else 0.0
    ext_key_recall = ext_key_hits / ext_total if ext_total else 0.0
    ext_mrr = ext_mrr / ext_total if ext_total else 0.0

    # --- Investigative ---
    inv_hits = 0

    with connect() as conn:
        for i, (question_id, question, expected_key) in enumerate(investigative_rows, 1):
            embedding = client.embed([question])[0]

            winning_keys, _ = find_winning_voyage_keys(conn, embedding, top_k=args.top_k_1)
            hit = expected_key in winning_keys
            if hit:
                inv_hits += 1

            if i % 50 == 0:
                print(f"  [investigative] {i}/{len(investigative_rows)} — key recall: {inv_hits/i:.1%}")

    inv_total = len(investigative_rows)
    inv_recall = inv_hits / inv_total if inv_total else 0.0

    # --- Log summaries ---
    with connect() as conn:
        log_retrieval_run(
            conn,
            run_id=run_id,
            test_type="chunk_retrieval",
            question_type="extractive",
            top_k=args.top_k_2,
            total=ext_total,
            hits=ext_hits,
            recall=ext_recall,
        )
        log_retrieval_run(
            conn,
            run_id=run_id,
            test_type="chunk_retrieval",
            question_type="investigative",
            top_k=args.top_k_1,
            total=inv_total,
            hits=inv_hits,
            recall=inv_recall,
        )

    print(f"\nDone. run_id={run_id}")
    print(f"Extractive   ({ext_total}): key recall: {ext_key_recall:.1%} | chunk recall: {ext_recall:.1%} | MRR: {ext_mrr:.4f}")
    print(f"Investigative ({inv_total}): key recall: {inv_recall:.1%}")


if __name__ == "__main__":
    main()
