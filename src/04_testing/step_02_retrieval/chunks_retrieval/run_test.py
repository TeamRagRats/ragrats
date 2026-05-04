"""
End-to-end chunk retrieval recall test.

Mirrors the full production pipeline for every ground_truth row:
  1. Embed the question
  2. find_winning_voyage_keys  (step 1)
  3. retrieve_chunks from winning keys (step 2)
  4. expand_chunks by ±expand_window neighbors

Hit = expected chunk_id appears in the expanded set.

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
    __package__ = "src.testing.retrieval.chunks"

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
    p = argparse.ArgumentParser(description="End-to-end chunk retrieval recall test")
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
        rows = conn.execute("""
            SELECT question_id, question, voyage_key, source_chunk_id::text
            FROM ground_truth
            WHERE source_chunk_id IS NOT NULL
            ORDER BY question_id
        """).fetchall()

    if not rows:
        print("No ground_truth rows found.")
        return

    print(
        f"Questions: {len(rows)} | top_k_1: {args.top_k_1} | top_k_2: {args.top_k_2} "
        f"| expand: ±{args.expand_window} | embed: {args.embed_url}"
    )

    client = EmbedClient(base_url=args.embed_url)
    run_id = str(uuid.uuid4())

    hits = 0
    key_hits = 0
    reciprocal_rank_sum = 0.0

    with connect() as conn:
        for i, (question_id, question, expected_key, expected_chunk_id) in enumerate(rows, 1):
            embedding = client.embed([question])[0]

            # Step 1 — find winning voyage_key(s)
            winning_keys, vote_counts = find_winning_voyage_keys(
                conn, embedding, top_k=args.top_k_1
            )
            key_hit = expected_key in winning_keys
            if key_hit:
                key_hits += 1

            # Step 2 — retrieve chunks from winning keys
            anchor_chunks = retrieve_chunks(
                conn, embedding, voyage_keys=winning_keys, top_k=args.top_k_2
            )
            expanded_chunks = expand_chunks(conn, anchor_chunks, window=args.expand_window)

            expanded_chunk_ids = [c.chunk_id for c in expanded_chunks]
            rank = _compute_chunk_rank(expected_chunk_id, anchor_chunks)
            hit = expected_chunk_id in expanded_chunk_ids

            if hit:
                hits += 1
            if rank is not None:
                reciprocal_rank_sum += 1.0 / rank

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
                print(
                    f"  {i}/{len(rows)} — key recall: {key_hits}/{i} ({key_hits/i:.1%}) "
                    f"| chunk recall: {hits}/{i} ({hits/i:.1%})"
                )

    total = len(rows)
    recall = hits / total if total else 0.0
    key_recall = key_hits / total if total else 0.0
    mrr = reciprocal_rank_sum / total if total else 0.0

    with connect() as conn:
        log_retrieval_run(
            conn,
            run_id=run_id,
            test_type="chunk_retrieval",
            top_k=args.top_k_2,
            total=total,
            hits=hits,
            recall=recall,
        )

    print(f"\nDone. run_id={run_id}")
    print(f"Voyage key recall@{args.top_k_1}: {key_hits}/{total} ({key_recall:.1%})")
    print(f"Chunk recall@{args.top_k_2}+expand±{args.expand_window}: {hits}/{total} ({recall:.1%})")
    print(f"MRR@{args.top_k_2}:                                       {mrr:.4f}")


if __name__ == "__main__":
    main()
