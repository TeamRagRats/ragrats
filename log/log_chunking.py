from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

import psycopg


def log_chunking_pending(
    conn: psycopg.Connection,
    source_type: str,
    source_id: str,
    voyage_key: str,
    started_at: datetime,
    run_id: Optional[UUID],
) -> None:
    """Records that a source has started chunking."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO chunking_logging
                (source_type, source_id, voyage_key, started_at, status, run_id)
            VALUES (%s, %s, %s, %s, 'pending', %s)
            ON CONFLICT (source_type, source_id) DO UPDATE SET
                voyage_key    = EXCLUDED.voyage_key,
                started_at    = EXCLUDED.started_at,
                finished_at   = NULL,
                duration_ms   = NULL,
                status        = 'pending',
                n_chunks      = NULL,
                char_count    = NULL,
                error_message = NULL,
                run_id        = EXCLUDED.run_id
            """,
            (source_type, source_id, voyage_key, started_at,
             str(run_id) if run_id else None),
        )
    conn.commit()


def log_chunking_finished(
    conn: psycopg.Connection,
    source_type: str,
    source_id: str,
    finished_at: datetime,
    duration_ms: int,
    status: str,
    n_chunks: Optional[int] = None,
    char_count: Optional[int] = None,
    error_message: Optional[str] = None,
    total_tokens: Optional[int] = None,
    truncated: bool = False,
) -> None:
    """Records the outcome of a chunking job."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE chunking_logging SET
                finished_at   = %s,
                duration_ms   = %s,
                status        = %s,
                n_chunks      = %s,
                char_count    = %s,
                error_message = %s,
                total_tokens  = %s,
                truncated     = %s
            WHERE source_type = %s AND source_id = %s
            """,
            (finished_at, duration_ms, status, n_chunks, char_count,
             error_message, total_tokens, truncated, source_type, source_id),
        )
    conn.commit()
