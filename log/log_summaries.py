from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

import psycopg


def log_summary_pending(
    conn: psycopg.Connection,
    summary_type: str,
    entity_key: str,
    voyage_key: str,
    started_at: datetime,
    run_id: Optional[UUID],
    batch_idx: int,
) -> None:
    """Records that a summary job has started."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO summaries_logging
                (summary_type, entity_key, voyage_key, started_at, status, run_id, batch_idx)
            VALUES (%s, %s, %s, %s, 'pending', %s, %s)
            ON CONFLICT (summary_type, entity_key) DO UPDATE SET
                voyage_key  = EXCLUDED.voyage_key,
                started_at  = EXCLUDED.started_at,
                finished_at = NULL,
                duration_ms = NULL,
                status      = 'pending',
                error_message = NULL,
                input_tokens  = NULL,
                output_tokens = NULL,
                run_id      = EXCLUDED.run_id,
                batch_idx   = EXCLUDED.batch_idx
            """,
            (summary_type, entity_key, voyage_key, started_at,
             str(run_id) if run_id else None, batch_idx),
        )
    conn.commit()


def log_summary_finished(
    conn: psycopg.Connection,
    summary_type: str,
    entity_key: str,
    finished_at: datetime,
    duration_ms: int,
    status: str,
    error_message: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
) -> None:
    """Records the outcome of a summary job."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE summaries_logging SET
                finished_at   = %s,
                duration_ms   = %s,
                status        = %s,
                error_message = %s,
                input_tokens  = %s,
                output_tokens = %s
            WHERE summary_type = %s AND entity_key = %s
            """,
            (finished_at, duration_ms, status, error_message,
             input_tokens, output_tokens, summary_type, entity_key),
        )
    conn.commit()
