"""
Isolated chunk retrieval test — step 2 only.

Feeds the correct voyage_key from ground truth directly to retrieve_chunks,
bypassing step 1 entirely. This measures how well step 2 performs given a
perfect voyage key, making it independent of step 1 errors.

Only runs on extractive questions (question_type='extractive'), since those
have a single known source_chunk_id to evaluate against.

Run on SPARK where both postgres and the embed server are reachable:
    python run_test.py
    python run_test.py --top-k 20 --expand-window 2
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
    __package__ = "src.testing.retrieval.chunk"

import argparse
import uuid

from core.db import connect
from clients.embed_client import EmbedClient, DEFAULT_BASE_URL
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
    p = argparse.ArgumentParser(description="Isolated chunk retrieval test (step 2 only)")
    p.add_argument("--top-k", type=int, default=20, dest="top_k",
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
            WHERE question_type = 'extractive'
            ORDER BY question_id
        """).fetchall()

    print(
        f"Extractive: {len(rows)} | top_k: {args.top_k} | expand: ±{args.expand_window}"
    )

    client = EmbedClient(base_url=args.embed_url)
    run_id = str(uuid.uuid4())

    hits = 0
    mrr = 0.0

    with connect() as conn:
        for i, (question_id, question, expected_key, expected_chunk_id) in enumerate(rows, 1):
            embedding = client.embed([question])[0]

            anchor_chunks = retrieve_chunks(
                conn, embedding, voyage_keys=[expected_key], top_k=args.top_k
            )
            expanded_chunks = expand_chunks(conn, anchor_chunks, window=args.expand_window)

            expanded_chunk_ids = [c.chunk_id for c in expanded_chunks]
            rank = _compute_chunk_rank(expected_chunk_id, anchor_chunks)
            hit = expected_chunk_id in expanded_chunk_ids

            if hit:
                hits += 1
            if rank is not None:
                mrr += 1.0 / rank

            log_chunk_retrieval_testing(
                conn,
                run_id=run_id,
                question_id=question_id,
                top_k=args.top_k,
                expected_source_id=expected_chunk_id,
                returned_source_ids=expanded_chunk_ids,
                hit=hit,
                source_rank=rank,
            )

            if i % 50 == 0:
                print(f"  {i}/{len(rows)} — chunk recall: {hits/i:.1%}")

    total = len(rows)
    recall = hits / total if total else 0.0
    mrr = mrr / total if total else 0.0

    with connect() as conn:
        log_retrieval_run(
            conn,
            run_id=run_id,
            test_type="chunk_retrieval_isolated",
            question_type="extractive",
            top_k=args.top_k,
            total=total,
            hits=hits,
            recall=recall,
        )

    print(f"\nDone. run_id={run_id}")
    print(f"Extractive ({total}): chunk recall: {recall:.1%} | MRR: {mrr:.4f}")


if __name__ == "__main__":
    main()
