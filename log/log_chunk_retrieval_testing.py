from __future__ import annotations

import psycopg


def log_chunk_retrieval_testing(
    conn: psycopg.Connection,
    *,
    run_id: str,
    question_id: str,
    top_k: int,
    expected_source_id: str,
    returned_source_ids: list[str],
    hit: bool,
    source_rank: int | None,
) -> None:
    """Logs a single question result to the test_chunk_retrieval_logging table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO test_chunk_retrieval_logging
                (run_id, question_id, top_k, expected_source_id, returned_source_ids, hit, source_rank)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                question_id,
                top_k,
                expected_source_id,
                returned_source_ids,
                hit,
                source_rank,
            ),
        )
    conn.commit()
