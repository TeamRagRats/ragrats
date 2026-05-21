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
    expected_source: str,
    returned_source_ids: list[str],
    hit: bool,
    source_rank: int | None,
    chunks: list[dict],
    flags: dict,
) -> None:
    """Logs a single question result to the test_retrieval_chunk_logging table.

    hit/source_rank are source-level (thread-level for emails); chunk-level
    recall is retired. chunks: retrieved-chunk metadata (no text). flags: the
    CLI flags the run used. Both stored as JSONB so the run is self-describing.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO test_retrieval_chunk_logging
                (run_id, question_id, category, question, expected_source,
                 returned_source_ids, hit, source_rank, chunks, flags)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                question_id,
                category,
                question,
                expected_source,
                returned_source_ids,
                hit,
                source_rank,
                json.dumps(chunks),
                json.dumps(flags),
            ),
        )
    conn.commit()
