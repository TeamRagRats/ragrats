from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

import psycopg


def log_embedding_pending(
    conn: psycopg.Connection,
    run_id: UUID,
    batch_idx: int,
    n_chunks: int,
    started_at: datetime,
) -> None:
    """Records that an embedding batch has started."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO embedding_logging
                (run_id, batch_idx, n_chunks, started_at, status)
            VALUES (%s, %s, %s, %s, 'pending')
            ON CONFLICT (run_id, batch_idx) DO UPDATE SET
                n_chunks      = EXCLUDED.n_chunks,
                started_at    = EXCLUDED.started_at,
                finished_at   = NULL,
                duration_ms   = NULL,
                status        = 'pending',
                error_message = NULL,
                model         = NULL
            """,
            (str(run_id), batch_idx, n_chunks, started_at),
        )
    conn.commit()


def log_embedding_finished(
    conn: psycopg.Connection,
    run_id: UUID,
    batch_idx: int,
    finished_at: datetime,
    duration_ms: int,
    status: str,
    model: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    """Records the outcome of an embedding batch."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE embedding_logging SET
                finished_at   = %s,
                duration_ms   = %s,
                status        = %s,
                model         = %s,
                error_message = %s
            WHERE run_id = %s AND batch_idx = %s
            """,
            (finished_at, duration_ms, status, model, error_message,
             str(run_id), batch_idx),
        )
    conn.commit()
