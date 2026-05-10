from __future__ import annotations

from typing import Any

import psycopg

from step_06_embedding.email_context.db import upsert_chunks  # noqa: F401


def get_pending_emails(
    conn: psycopg.Connection, limit: int | None
) -> list[dict]:
    """Emails with an OK summary not yet embedded with strategy='summary'."""
    sql = """
        SELECT s.email_id, s.thread_id, s.voyage_key, s.summary
        FROM email_summaries s
        WHERE s.status = 'ok'
          AND s.summary IS NOT NULL
          AND s.summary <> ''
          AND NOT EXISTS (
              SELECT 1 FROM chunks c
              WHERE c.source_type = 'email'
                AND c.strategy    = 'summary'
                AND c.source_id   = s.email_id::text
          )
        ORDER BY s.email_id
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        sql += " LIMIT %s"
        params = (limit,)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [
            {
                "email_id":  row[0],
                "thread_id": row[1],
                "voyage_key": row[2],
                "summary":   row[3],
            }
            for row in cur.fetchall()
        ]
