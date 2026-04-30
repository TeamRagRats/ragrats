from __future__ import annotations

# Read/write helpers for the llm_load_queue view and llm_structured table.
# All inserts are UPSERTs keyed on sha256 so re-runs cleanly overwrite prior state.

from dataclasses import dataclass
from typing import Optional

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
