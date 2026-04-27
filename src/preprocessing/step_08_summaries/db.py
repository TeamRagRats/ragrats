from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

import psycopg


def log_pending(
    conn: psycopg.Connection,
    email_id: str,
    voyage_key: str,
    attach_count: int,
    started_at: datetime,
    run_id: Optional[UUID],
    batch_idx: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO summaries_logging
                (email_id, voyage_key, attach_count, started_at, status, batch_idx, run_id)
            VALUES (%s, %s, %s, %s, 'pending', %s, %s)
            ON CONFLICT (email_id) DO UPDATE SET
                voyage_key    = EXCLUDED.voyage_key,
                attach_count  = EXCLUDED.attach_count,
                started_at    = EXCLUDED.started_at,
                finished_at   = NULL,
                duration_ms   = NULL,
                status        = 'pending',
                error_message = NULL,
                input_tokens  = NULL,
                output_tokens = NULL,
                batch_idx     = EXCLUDED.batch_idx,
                run_id        = EXCLUDED.run_id
            """,
            (email_id, voyage_key, attach_count, started_at, batch_idx,
             str(run_id) if run_id else None),
        )
    conn.commit()


def log_finished(
    conn: psycopg.Connection,
    email_id: str,
    finished_at: datetime,
    duration_ms: int,
    status: str,
    error_message: Optional[str],
    input_tokens: Optional[int],
    output_tokens: Optional[int],
) -> None:
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
            WHERE email_id = %s
            """,
            (finished_at, duration_ms, status, error_message,
             input_tokens, output_tokens, email_id),
        )
    conn.commit()
