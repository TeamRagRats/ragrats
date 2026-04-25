from __future__ import annotations

# Write helpers for the docling + docling_logging tables. All inserts are
# UPSERTs keyed on sha256 so re-runs overwrite prior state cleanly.

from datetime import datetime
from typing import Optional
from uuid import UUID

import psycopg


def upsert_docling(
    conn: psycopg.Connection,
    sha256: str,
    markdown: Optional[str],
    char_count: int,
    token_count: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO docling (sha256, markdown, char_count, token_count, processed_at) "
            "VALUES (%s, %s, %s, %s, now()) "
            "ON CONFLICT (sha256) DO UPDATE SET "
            "  markdown = EXCLUDED.markdown, "
            "  char_count = EXCLUDED.char_count, "
            "  token_count = EXCLUDED.token_count, "
            "  processed_at = now()",
            (sha256, markdown, char_count, token_count),
        )
    conn.commit()


def log_file_pending(
    conn: psycopg.Connection,
    sha256: str,
    file_path: str,
    file_type: str,
    file_size_bytes: int,
    started_at: datetime,
    run_id: Optional[UUID],
    batch_idx: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO docling_logging "
            "(sha256, file_path, file_type, file_size_bytes, started_at, status, batch_idx, run_id) "
            "VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s) "
            "ON CONFLICT (sha256) DO UPDATE SET "
            "  file_path = EXCLUDED.file_path, "
            "  file_type = EXCLUDED.file_type, "
            "  file_size_bytes = EXCLUDED.file_size_bytes, "
            "  started_at = EXCLUDED.started_at, "
            "  finished_at = NULL, "
            "  duration_ms = NULL, "
            "  status = 'pending', "
            "  error_message = NULL, "
            "  batch_idx = EXCLUDED.batch_idx, "
            "  run_id = EXCLUDED.run_id",
            (sha256, file_path, file_type, file_size_bytes, started_at,
             batch_idx, str(run_id) if run_id else None),
        )
    conn.commit()


def log_file_finished(
    conn: psycopg.Connection,
    sha256: str,
    finished_at: datetime,
    duration_ms: int,
    status: str,
    error_message: Optional[str],
    char_count: Optional[int],
    token_count: Optional[int],
    gpu_util_pct: Optional[int],
    gpu_mem_pct: Optional[float],
    ram_pct: Optional[float],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE docling_logging SET "
            "  finished_at = %s, duration_ms = %s, status = %s, error_message = %s, "
            "  char_count = %s, token_count = %s, "
            "  gpu_util_pct = %s, gpu_mem_pct = %s, ram_pct = %s "
            "WHERE sha256 = %s",
            (finished_at, duration_ms, status, error_message,
             char_count, token_count, gpu_util_pct, gpu_mem_pct, ram_pct, sha256),
        )
    conn.commit()
