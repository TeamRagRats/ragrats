from __future__ import annotations

# DB queries for attachment plain chunking.
# get_attachment_data and upsert_chunks are identical to attachment_late —
# imported directly to avoid duplication.

from typing import Any

import psycopg

from step_06_embedding.attachment_late.db import get_attachment_data, upsert_chunks  # noqa: F401


def get_pending_sha256s(
    conn: psycopg.Connection,
    voyage: str | None = None,
    limit: int | None = None,
) -> list[str]:
    """llm_structured rows not yet plain-embedded as attachments."""
    parts = [
        """
        SELECT ls.sha256
        FROM llm_structured ls
        JOIN attachments a ON a.sha256 = ls.sha256
        WHERE ls.structured_md IS NOT NULL
          AND ls.structured_md <> ''
          AND NOT EXISTS (
              SELECT 1 FROM chunks c
              WHERE c.source_type = 'attachment'
                AND c.strategy    = 'plain'
                AND c.source_id   = ls.sha256
          )
        """
    ]
    params: list[Any] = []

    if voyage is not None:
        parts.append("AND a.voyage_key = %s")
        params.append(voyage)

    parts.append("ORDER BY ls.sha256")

    if limit is not None:
        parts.append("LIMIT %s")
        params.append(limit)

    with conn.cursor() as cur:
        cur.execute(" ".join(parts), params)
        return [row[0] for row in cur.fetchall()]
