from __future__ import annotations

# DB queries for email plain chunking: pending emails (just body_cleaned, no
# summary join) and chunk upserts (embedding written as halfvec).

from typing import Any, Sequence

import psycopg


def get_pending_emails(
    conn: psycopg.Connection, chunker: str, limit: int | None
) -> list[dict]:
    """Emails with body_cleaned not yet plain-chunked with this chunker."""
    sql = """
        SELECT e.email_id, e.voyage_key, e.thread_id, e.body_cleaned
        FROM emails e
        WHERE e.body_cleaned IS NOT NULL
          AND e.body_cleaned <> ''
          AND NOT EXISTS (
              SELECT 1 FROM chunks c
              WHERE c.source_type = 'email'
                AND c.strategy    = 'plain'
                AND c.chunker     = %s
                AND c.source_id   = e.email_id::text
          )
        ORDER BY e.email_id
    """
    params: tuple[Any, ...] = (chunker,)
    if limit is not None:
        sql += " LIMIT %s"
        params = (chunker, limit)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [
            {
                "email_id": row[0],
                "voyage_key": row[1],
                "thread_id": row[2],
                "body_cleaned": row[3],
            }
            for row in cur.fetchall()
        ]


def upsert_chunks(conn: psycopg.Connection, rows: Sequence[dict]) -> None:
    """Batch upsert chunk rows. Each row dict must contain:
        source_type, source_id, voyage_key, thread_id, chunk_index,
        text, embedding (halfvec literal str), char_count, strategy, chunker, model.
    """
    if not rows:
        return
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(
                """
                INSERT INTO chunks
                    (source_type, source_id, voyage_key, thread_id, chunk_index,
                     text, embedding, char_count, strategy, chunker, model)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s::halfvec, %s, %s, %s, %s)
                ON CONFLICT (source_type, source_id, strategy, chunker, chunk_index)
                DO UPDATE SET
                    voyage_key = EXCLUDED.voyage_key,
                    thread_id  = EXCLUDED.thread_id,
                    text       = EXCLUDED.text,
                    embedding  = EXCLUDED.embedding,
                    char_count = EXCLUDED.char_count,
                    model      = EXCLUDED.model
                """,
                (
                    r["source_type"],
                    r["source_id"],
                    r["voyage_key"],
                    r["thread_id"],
                    r["chunk_index"],
                    r["text"],
                    r["embedding"],
                    r["char_count"],
                    r["strategy"],
                    r["chunker"],
                    r["model"],
                ),
            )
    conn.commit()
