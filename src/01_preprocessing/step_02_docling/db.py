from __future__ import annotations

# Write helpers for the docling table. All inserts are
# UPSERTs keyed on sha256 so re-runs overwrite prior state cleanly.

from typing import Optional

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
