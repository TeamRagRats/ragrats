from __future__ import annotations

# Read/write helpers for the llm_load_queue view, llm_structured table, and
# llm_logging table. All inserts are UPSERTs keyed on sha256 so re-runs cleanly
# overwrite prior state.

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

import psycopg


@dataclass
class QueueItem:
    sha256: str
    markdown: str
    char_count: int
    email_id: str
    voyage_key: str
    file_path: str
    file_type: str


def fetch_pending(
    conn: psycopg.Connection,
    voyage: Optional[str] = None,
    sha256_filter: Optional[set[str]] = None,
    limit: Optional[int] = None,
    include_done: bool = False,
) -> list[QueueItem]:
    """Pending = anything in llm_load_queue that is not yet done/skipped in
    llm_logging. error rows are reprocessed automatically."""
    from psycopg import sql as pgsql

    parts: list[pgsql.Composable] = [pgsql.SQL(
        "SELECT q.sha256, q.markdown, q.char_count, q.email_id, q.voyage_key, "
        "       q.file_path, q.file_type "
        "FROM   llm_load_queue q "
        "LEFT JOIN llm_logging l ON l.sha256 = q.sha256 "
    )]
    params: list = []

    if include_done:
        parts.append(pgsql.SQL("WHERE TRUE "))
    else:
        # 'pending' rows older than 30 min are treated as orphaned (vLLM crashed
        # or container got recreated mid-batch) and re-fetched.
        parts.append(pgsql.SQL(
            "WHERE (l.status IS NULL "
            "       OR l.status = 'error' "
            "       OR (l.status = 'pending' AND l.started_at < now() - INTERVAL '30 minutes')) "
        ))

    if voyage:
        parts.append(pgsql.SQL("AND q.voyage_key = %s "))
        params.append(voyage)

    if sha256_filter:
        parts.append(pgsql.SQL("AND q.sha256 = ANY(%s) "))
        params.append(list(sha256_filter))

    parts.append(pgsql.SQL("ORDER BY q.char_count ASC "))
    if limit:
        parts.append(pgsql.SQL("LIMIT %s"))
        params.append(limit)

    items: list[QueueItem] = []
    with conn.cursor() as cur:
        cur.execute(pgsql.Composed(parts), params)
        for sha, md, char_count, email_id, voyage_key, file_path, file_type in cur.fetchall():
            items.append(QueueItem(
                sha256=sha,
                markdown=md or "",
                char_count=int(char_count or 0),
                email_id=str(email_id),
                voyage_key=voyage_key,
                file_path=file_path,
                file_type=file_type or "",
            ))
    return items


def reset_errors(conn: psycopg.Connection, sha256_filter: Optional[set[str]] = None) -> int:
    """Delete error rows from llm_logging so they re-enter the pending pool.
    Used by --fresh."""
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


def log_pending(
    conn: psycopg.Connection,
    item: QueueItem,
    size_category: str,
    mode: str,
    started_at: datetime,
    run_id: Optional[UUID],
    batch_idx: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO llm_logging "
            "(sha256, file_path, file_type, char_count, size_category, mode, "
            " started_at, status, batch_idx, run_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s) "
            "ON CONFLICT (sha256) DO UPDATE SET "
            "  file_path = EXCLUDED.file_path, "
            "  file_type = EXCLUDED.file_type, "
            "  char_count = EXCLUDED.char_count, "
            "  size_category = EXCLUDED.size_category, "
            "  mode = EXCLUDED.mode, "
            "  started_at = EXCLUDED.started_at, "
            "  finished_at = NULL, "
            "  duration_ms = NULL, "
            "  status = 'pending', "
            "  error_message = NULL, "
            "  input_tokens = NULL, "
            "  output_tokens = NULL, "
            "  gpu_util_pct = NULL, "
            "  gpu_mem_pct = NULL, "
            "  ram_pct = NULL, "
            "  batch_idx = EXCLUDED.batch_idx, "
            "  run_id = EXCLUDED.run_id",
            (item.sha256, item.file_path, item.file_type, item.char_count,
             size_category, mode, started_at, batch_idx,
             str(run_id) if run_id else None),
        )
    conn.commit()


def log_finished(
    conn: psycopg.Connection,
    sha256: str,
    finished_at: datetime,
    duration_ms: int,
    status: str,
    error_message: Optional[str],
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    gpu_util_pct: Optional[int],
    gpu_mem_pct: Optional[float],
    ram_pct: Optional[float],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE llm_logging SET "
            "  finished_at = %s, duration_ms = %s, status = %s, error_message = %s, "
            "  input_tokens = %s, output_tokens = %s, "
            "  gpu_util_pct = %s, gpu_mem_pct = %s, ram_pct = %s "
            "WHERE sha256 = %s",
            (finished_at, duration_ms, status, error_message,
             input_tokens, output_tokens,
             gpu_util_pct, gpu_mem_pct, ram_pct, sha256),
        )
    conn.commit()


def upsert_structured(
    conn: psycopg.Connection,
    sha256: str,
    mode: str,
    document_type: Optional[str],
    structured_md: Optional[str],
    input_token_count: int,
    output_token_count: int,
    model_name: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO llm_structured "
            "(sha256, mode, document_type, structured_md, "
            " input_token_count, output_token_count, model_name, processed_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, now()) "
            "ON CONFLICT (sha256) DO UPDATE SET "
            "  mode = EXCLUDED.mode, "
            "  document_type = EXCLUDED.document_type, "
            "  structured_md = EXCLUDED.structured_md, "
            "  input_token_count = EXCLUDED.input_token_count, "
            "  output_token_count = EXCLUDED.output_token_count, "
            "  model_name = EXCLUDED.model_name, "
            "  processed_at = now()",
            (sha256, mode, document_type, structured_md,
             input_token_count, output_token_count, model_name),
        )
    conn.commit()


def queue_stats(conn: psycopg.Connection, voyage: Optional[str] = None) -> dict:
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
