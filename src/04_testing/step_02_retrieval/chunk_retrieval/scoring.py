"""Per-question scoring + logging for the chunk retrieval test.

Shared by run_test.py and the matrix runners: given the retrieved chunks for
one question, computes thread/email rank, logs the per-question row, and returns
the two ranks so the caller can aggregate recall/MRR.
"""
from __future__ import annotations

from log.log_chunk_retrieval_testing import log_chunk_retrieval_testing
from source_match import (
    canonical_email,
    canonical_thread,
    compute_email_rank,
    compute_thread_rank,
    serialize_chunks,
)


def score_and_log_question(
    conn,
    *,
    run_id: str,
    category: str,
    question_id,
    question: str,
    chunks: list,
    expected_source_type: str,
    expected_source_id,
    expected_strategy: str,
    email_thread_map: dict[str, str],
    attach_email_map: dict[str, str],
    flags: dict,
) -> tuple[int | None, int | None]:
    """Returns (thread_rank, email_rank); None means no hit. Logs one row."""
    expected_email_id = expected_source_id if expected_source_type == "email" else None
    expected_thread_id = (
        email_thread_map.get(expected_source_id) if expected_source_type == "email" else None
    )
    expected_canonical = canonical_thread(
        expected_source_type, expected_source_id, expected_strategy,
        email_thread_map, attach_email_map,
    )

    thread_rank = compute_thread_rank(
        chunks, expected_canonical, email_thread_map, attach_email_map,
    )
    email_rank = compute_email_rank(chunks, expected_email_id, attach_email_map)

    returned_email_ids = [
        canonical_email(c.source_type, c.source_id, c.strategy, attach_email_map)
        for c in chunks
    ]
    returned_thread_ids = [
        canonical_thread(
            c.source_type, c.source_id, c.strategy,
            email_thread_map, attach_email_map,
        )
        for c in chunks
    ]
    log_chunk_retrieval_testing(
        conn,
        run_id=run_id,
        question_id=question_id,
        category=category,
        question=question,
        expected_email=expected_email_id,
        expected_thread=expected_thread_id,
        returned_email_ids=returned_email_ids,
        returned_thread_ids=returned_thread_ids,
        thread_hit=thread_rank is not None,
        thread_rank=thread_rank,
        email_hit=email_rank is not None,
        email_rank=email_rank,
        chunks=serialize_chunks(chunks),
        flags=flags,
    )
    return thread_rank, email_rank
