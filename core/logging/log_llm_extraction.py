from __future__ import annotations

from datetime import datetime
from typing import Optional, Any
from uuid import UUID

import psycopg

def log_extraction_pending(
    conn: psycopg.Connection,
    sha256: str,
    file_path: str,
    file_type: str,
    char_count: int,
    size_category: str,
    mode: str,
    started_at: datetime,
    run_id: Optional[UUID],
    batch_idx: int,
) -> None:
    """Records that a document has started LLM extraction."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO llm_logging 
                (sha256, file_path, file_type, char_count, size_category, mode, 
                 started_at, status, batch_idx, run_id) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s) 
            ON CONFLICT (sha256) DO UPDATE SET 
              file_path = EXCLUDED.file_path, 
              file_type = EXCLUDED.file_type, 
              char_count = EXCLUDED.char_count, 
              size_category = EXCLUDED.size_category, 
              mode = EXCLUDED.mode, 
              started_at = EXCLUDED.started_at, 
              finished_at = NULL, 
              duration_ms = NULL, 
              status = 'pending', 
              error_message = NULL, 
              input_tokens = NULL, 
              output_tokens = NULL, 
              gpu_util_pct = NULL, 
              gpu_mem_pct = NULL, 
              ram_pct = NULL, 
              batch_idx = EXCLUDED.batch_idx, 
              run_id = EXCLUDED.run_id
            """,
            (sha256, file_path, file_type, char_count,
             size_category, mode, started_at, batch_idx,
             str(run_id) if run_id else None),
        )
    conn.commit()

def log_extraction_finished(
    conn: psycopg.Connection,
    sha256: str,
    finished_at: datetime,
    duration_ms: int,
    status: str,
    error_message: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    gpu_util_pct: Optional[int] = None,
    gpu_mem_pct: Optional[float] = None,
    ram_pct: Optional[float] = None,
) -> None:
    """Records the outcome and resource usage of an LLM extraction task."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE llm_logging SET 
              finished_at = %s, duration_ms = %s, status = %s, error_message = %s, 
              input_tokens = %s, output_tokens = %s, 
              gpu_util_pct = %s, gpu_mem_pct = %s, ram_pct = %s 
            WHERE sha256 = %s
            """,
            (finished_at, duration_ms, status, error_message,
             input_tokens, output_tokens,
             gpu_util_pct, gpu_mem_pct, ram_pct, sha256),
        )
    conn.commit()

def reset_extraction_errors(conn: psycopg.Connection, sha256_filter: Optional[set[str]] = None) -> int:
    """Delete error rows from llm_logging so they re-enter the pending pool."""
    with conn.cursor() as cur:
        if sha256_filter:
            cur.execute(
                "DELETE FROM llm_logging WHERE status = 'error' AND sha256 = ANY(%s)",
                (list(sha256_filter),),
            )
        else:
            cur.execute("DELETE FROM llm_logging WHERE status = 'error'")
        deleted = cur.rowcount
    conn.commit()
    return deleted

def get_extraction_stats(conn: psycopg.Connection, voyage: Optional[str] = None) -> dict[str, Any]:
    """Returns queue and processing statistics for LLM extraction."""
    params: tuple = (voyage,) if voyage else ()
    with conn.cursor() as cur:
        if voyage:
            cur.execute("SELECT COUNT(*) FROM llm_load_queue WHERE voyage_key = %s", params)
        else:
            cur.execute("SELECT COUNT(*) FROM llm_load_queue")
        row = cur.fetchone()
        total = row[0] if row else 0

        if voyage:
            cur.execute(
                "SELECT status, COUNT(*) FROM llm_logging l "
                "JOIN llm_load_queue q ON q.sha256 = l.sha256 "
                "WHERE q.voyage_key = %s GROUP BY status",
                params,
            )
        else:
            cur.execute("SELECT status, COUNT(*) FROM llm_logging GROUP BY status")
        by_status = dict(cur.fetchall())
    return {"queue_total": total, "logging_by_status": by_status}
