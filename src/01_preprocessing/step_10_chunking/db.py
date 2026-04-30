from __future__ import annotations

# DB helpers for the chunking step.
# Reads pending summaries and upserts finished chunks into the chunks table.

import psycopg
from psycopg.rows import dict_row


def get_pending_voyages(conn: psycopg.Connection) -> list[str]:
    """Return voyage_keys that have a voyage summary but no chunks yet."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT vs.voyage_key
            FROM voyage_summaries vs
            WHERE vs.summary IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM chunks c
                  WHERE c.source_type = 'voyage'
                    AND c.source_id = vs.voyage_key
              )
        """)
        return [row[0] for row in cur.fetchall()]


def get_voyage_summary(conn: psycopg.Connection, voyage_key: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT summary FROM voyage_summaries WHERE voyage_key = %s", (voyage_key,))
        row = cur.fetchone()
        return row[0] if row else None


def get_pending_emails(conn: psycopg.Connection) -> list[dict]:
    """Return email_id + voyage_key + summary for emails without a chunk yet."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT eas.email_id, eas.voyage_key, eas.summary
            FROM email_attach_summaries eas
            WHERE eas.status = 'ok'
              AND eas.summary IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM chunks c
                  WHERE c.source_type = 'email'
                    AND c.source_id = eas.email_id::text
              )
        """)
        return cur.fetchall()


def upsert_chunks(
    conn: psycopg.Connection,
    source_type: str,
    source_id: str,
    voyage_key: str,
    chunks: list[dict],
) -> int:
    """Insert chunks without embedding, skipping any (source_type, source_id, chunk_index) that already exist."""
    inserted = 0
    with conn.cursor() as cur:
        for chunk in chunks:
            cur.execute(
                """
                INSERT INTO chunks
                    (source_type, source_id, voyage_key, chunk_index, text, char_count)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_type, source_id, chunk_index) DO NOTHING
                """,
                (
                    source_type,
                    source_id,
                    voyage_key,
                    chunk["chunk_index"],
                    chunk["text"],
                    chunk["char_count"],
                ),
            )
            inserted += cur.rowcount
    conn.commit()
    return inserted
