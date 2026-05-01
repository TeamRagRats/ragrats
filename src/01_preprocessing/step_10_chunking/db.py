from __future__ import annotations

# DB helpers for the chunking step.
# Reads pending summaries and upserts finished chunks into the chunks table.

import psycopg
from psycopg.rows import dict_row


def get_pending_emails(conn: psycopg.Connection) -> list[dict]:
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
                    AND c.strategy = 'late'
              )
        """)
        return cur.fetchall()


def get_pending_threads(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT ts.thread_id, ts.voyage_key, ts.summary
            FROM thread_summaries ts
            WHERE ts.status = 'ok'
              AND ts.summary IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM chunks c
                  WHERE c.source_type = 'thread'
                    AND c.source_id = ts.thread_id::text
                    AND c.strategy = 'late'
              )
        """)
        return cur.fetchall()


def get_pending_phases(conn: psycopg.Connection) -> dict[str, list[dict]]:
    """Return phases grouped by voyage_key, sorted by phase_index ASC.
    Only returns voyages where at least one phase lacks a late_overlap chunk.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT ps.voyage_key, ps.phase_index, ps.summary
            FROM phase_summaries ps
            WHERE ps.status = 'ok'
              AND ps.summary IS NOT NULL
              AND ps.voyage_key IN (
                  SELECT DISTINCT ps2.voyage_key
                  FROM phase_summaries ps2
                  WHERE ps2.status = 'ok'
                    AND NOT EXISTS (
                        SELECT 1 FROM chunks c
                        WHERE c.source_type = 'phase'
                          AND c.source_id = ps2.voyage_key || '__' || ps2.phase_index
                          AND c.strategy = 'late_overlap'
                    )
              )
            ORDER BY ps.voyage_key, ps.phase_index ASC
        """)
        rows = cur.fetchall()

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["voyage_key"], []).append(row)
    return grouped


def upsert_chunks(
    conn: psycopg.Connection,
    source_type: str,
    source_id: str,
    voyage_key: str,
    strategy: str,
    chunks: list[dict],
) -> int:
    inserted = 0
    with conn.cursor() as cur:
        for chunk in chunks:
            cur.execute(
                """
                INSERT INTO chunks
                    (source_type, source_id, voyage_key, strategy, chunk_index, text, char_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_type, source_id, strategy, chunk_index) DO NOTHING
                """,
                (
                    source_type,
                    source_id,
                    voyage_key,
                    strategy,
                    chunk["chunk_index"],
                    chunk["text"],
                    chunk["char_count"],
                ),
            )
            inserted += cur.rowcount
    conn.commit()
    return inserted
