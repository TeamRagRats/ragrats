from __future__ import annotations

from typing import Any

import psycopg

from step_06_embedding.email_context.db import upsert_chunks  # noqa: F401


def get_pending(
    conn: psycopg.Connection,
    voyage: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """email_attach_summaries rows not yet embedded with strategy='summary'."""
    parts = [
        """
        SELECT a.email_id, e.thread_id, a.voyage_key, a.summary
        FROM email_attach_summaries a
        JOIN emails e ON e.email_id = a.email_id
        WHERE a.status = 'ok'
          AND a.summary IS NOT NULL
          AND a.summary <> ''
          AND NOT EXISTS (
              SELECT 1 FROM chunks c
              WHERE c.source_type = 'attachment'
                AND c.strategy    = 'summary'
                AND c.source_id   = a.email_id::text
          )
        """
    ]
    params: list[Any] = []

    if voyage is not None:
        parts.append("AND a.voyage_key = %s")
        params.append(voyage)

    parts.append("ORDER BY a.email_id")

    if limit is not None:
        parts.append("LIMIT %s")
        params.append(limit)

    with conn.cursor() as cur:
        cur.execute(" ".join(parts), params)
        return [
            {
                "email_id":  row[0],
                "thread_id": row[1],
                "voyage_key": row[2],
                "summary":   row[3],
            }
            for row in cur.fetchall()
        ]
