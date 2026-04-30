from __future__ import annotations

from datetime import datetime
from typing import Optional
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
