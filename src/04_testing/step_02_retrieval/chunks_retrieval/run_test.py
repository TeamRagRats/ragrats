"""
Chunk retrieval recall test.

For every ground_truth row, embeds the question, runs retrieve_chunks with the
known voyage_key, and logs hit@k + source rank to test_chunk_retrieval_logging
and a summary row to test_logging.

Run on SPARK where both postgres and the embed server are reachable:
    python run_test.py
    python run_test.py --top-k 50
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
from step_02_chunk_retrieval.retrieve_chunks import retrieve_chunks
from log.log_chunk_retrieval_testing import log_chunk_retrieval_testing
from log.log_testing import log_testing


def _compute_source_rank(expected_source_id: str, chunks: list) -> int | None:
    for i, chunk in enumerate(chunks, 1):
        if chunk.source_id == expected_source_id:
            return i
    return None


def main() -> None:
    p = argparse.ArgumentParser(description="Chunk retrieval recall test")
    p.add_argument("--top-k", type=int, default=20, dest="top_k",
                   help="Chunks to retrieve per question (default: 20)")
    p.add_argument("--embed-url", default=DEFAULT_BASE_URL,
                   help=f"Embed server base URL (default: {DEFAULT_BASE_URL})")
    args = p.parse_args()

    with connect() as conn:
        rows = conn.execute("""
            SELECT question_id, question, voyage_key, source_email_id::text
            FROM ground_truth
            WHERE source_email_id IS NOT NULL
            ORDER BY question_id
        """).fetchall()

    if not rows:
        print("No ground_truth rows found.")
        return

    print(f"Questions: {len(rows)} | top_k: {args.top_k} | embed: {args.embed_url}")

    client = EmbedClient(base_url=args.embed_url)
    run_id = str(uuid.uuid4())

    hits = 0
    reciprocal_rank_sum = 0.0

    with connect() as conn:
        for i, (question_id, question, voyage_key, expected_source_id) in enumerate(rows, 1):
            embedding = client.embed([question])[0]
            chunks = retrieve_chunks(conn, embedding, voyage_keys=[voyage_key], top_k=args.top_k)

            returned_source_ids = [c.source_id for c in chunks]
            hit = expected_source_id in returned_source_ids
            rank = _compute_source_rank(expected_source_id, chunks)

            if hit:
                hits += 1
            if rank is not None:
                reciprocal_rank_sum += 1.0 / rank

            log_chunk_retrieval_testing(
                conn,
                run_id=run_id,
                question_id=question_id,
                top_k=args.top_k,
                expected_source_id=expected_source_id,
                returned_source_ids=returned_source_ids,
                hit=hit,
                source_rank=rank,
            )

            if i % 50 == 0:
                print(f"  {i}/{len(rows)} — recall so far: {hits}/{i} ({hits/i:.1%})")

    total = len(rows)
    recall = hits / total if total else 0.0
    mrr = reciprocal_rank_sum / total if total else 0.0

    with connect() as conn:
        log_testing(
            conn,
            run_id=run_id,
            test_type="chunk_retrieval",
            top_k=args.top_k,
            total=total,
            hits=hits,
            recall=recall,
        )

    print(f"\nDone. run_id={run_id}")
    print(f"Recall@{args.top_k}: {hits}/{total} ({recall:.1%})")
    print(f"MRR@{args.top_k}:    {mrr:.4f}")


if __name__ == "__main__":
    main()
