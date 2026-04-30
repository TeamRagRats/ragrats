from __future__ import annotations

from uuid import UUID
import psycopg

def log_ingest(
    conn: psycopg.Connection,
    run_id: UUID,
    voyage_key: str,
    n_emails: int,
    n_threads: int,
    n_attachments: int,
    n_bytes: int,
    n_errors: int,
    wall_time_ms: int,
) -> None:
    """Logs per-voyage metrics for an ingest run."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ingest_logging 
                (run_id, voyage_key, n_emails, n_threads, n_attachments, n_bytes, n_errors, wall_time_ms) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(run_id),
                voyage_key,
                n_emails,
                n_threads,
                n_attachments,
                n_bytes,
                n_errors,
                wall_time_ms,
            ),
        )
    conn.commit()
