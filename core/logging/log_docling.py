from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID
import psycopg

def log_docling_pending(
    conn: psycopg.Connection,
    sha256: str,
    file_path: str,
    file_type: str,
    file_size_bytes: int,
    started_at: datetime,
    run_id: Optional[UUID],
    batch_idx: int,
) -> None:
    """Records that a file has started processing in Docling."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO docling_logging 
                (sha256, file_path, file_type, file_size_bytes, started_at, status, batch_idx, run_id) 
            VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s) 
            ON CONFLICT (sha256) DO UPDATE SET 
              file_path = EXCLUDED.file_path, 
              file_type = EXCLUDED.file_type, 
              file_size_bytes = EXCLUDED.file_size_bytes, 
              started_at = EXCLUDED.started_at, 
              finished_at = NULL, 
              duration_ms = NULL, 
              status = 'pending', 
              error_message = NULL, 
              batch_idx = EXCLUDED.batch_idx, 
              run_id = EXCLUDED.run_id
            """,
            (sha256, file_path, file_type, file_size_bytes, started_at,
             batch_idx, str(run_id) if run_id else None),
        )
    conn.commit()

def log_docling_finished(
    conn: psycopg.Connection,
    sha256: str,
    finished_at: datetime,
    duration_ms: int,
    status: str,
    error_message: Optional[str] = None,
    char_count: Optional[int] = None,
    token_count: Optional[int] = None,
    gpu_util_pct: Optional[int] = None,
    gpu_mem_pct: Optional[float] = None,
    ram_pct: Optional[float] = None,
) -> None:
    """Records the outcome and resource usage of a Docling task."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE docling_logging SET 
              finished_at = %s, duration_ms = %s, status = %s, error_message = %s, 
              char_count = %s, token_count = %s, 
              gpu_util_pct = %s, gpu_mem_pct = %s, ram_pct = %s 
            WHERE sha256 = %s
            """,
            (finished_at, duration_ms, status, error_message,
             char_count, token_count, gpu_util_pct, gpu_mem_pct, ram_pct, sha256),
        )
    conn.commit()
