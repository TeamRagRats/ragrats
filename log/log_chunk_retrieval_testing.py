from __future__ import annotations

import json

import psycopg


def log_chunk_retrieval_testing(
    conn: psycopg.Connection,
    *,
    run_id: str,
    question_id: str,
    category: str,
    question: str,
    expected_email: str | None,
    expected_thread: str | None,
    returned_email_ids: list[str | None],
    returned_thread_ids: list[str | None],
    thread_hit: bool,
    thread_rank: int | None,
    email_hit: bool,
    email_rank: int | None,
    chunks: list[dict],
    flags: dict,
) -> None:
    """Logs a single question result to the test_retrieval_chunk_logging table.

    Two recall levels are tracked: thread (chunk in the same email thread as
    the expected source) and email (chunk's parent email == expected source_id).
    email_hit always implies thread_hit. returned_email_ids and
    returned_thread_ids parallel the chunks list and may contain NULL
    elements for chunks we can't resolve. chunks: retrieved-chunk metadata
    plus the chunk text. flags: the CLI flags the run used. Both stored as
    JSONB so the run is self-describing.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO test_retrieval_chunk_logging
                (run_id, question_id, category, question,
                 expected_email, expected_thread,
                 returned_email_ids, returned_thread_ids,
                 thread_hit, thread_rank, email_hit, email_rank,
                 chunks, flags)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                question_id,
                category,
                question,
                expected_email,
                expected_thread,
                returned_email_ids,
                returned_thread_ids,
                thread_hit,
                thread_rank,
                email_hit,
                email_rank,
                json.dumps(chunks),
                json.dumps(flags),
            ),
        )
    conn.commit()
