from __future__ import annotations

import psycopg


def log_testing(
    conn: psycopg.Connection,
    *,
    run_id: str,
    test_type: str,
    top_k: int,
    total: int,
    hits: int,
    recall: float,
) -> None:
    """Logs a test run summary to the test_logging table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO test_logging (run_id, test_type, top_k, total, hits, recall)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (run_id, test_type, top_k, total, hits, recall),
        )
    conn.commit()
