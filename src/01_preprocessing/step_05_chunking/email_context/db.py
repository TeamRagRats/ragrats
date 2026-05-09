from __future__ import annotations

# DB queries for email context chunking: pending emails (joined with their
# prior-thread summary) and chunk upserts (embedding written as halfvec).

from typing import Any, Sequence

import psycopg


def get_pending_emails(
    conn: psycopg.Connection, limit: int | None
) -> list[dict]:
    """Emails with an OK summary that have not been context-chunked yet."""
    sql = """
        SELECT e.email_id, e.voyage_key, e.thread_id, e.body_cleaned, s.summary
        FROM emails e
        JOIN email_thread_summaries s ON s.email_id = e.email_id
        WHERE s.status = 'ok'
          AND e.body_cleaned IS NOT NULL
          AND e.body_cleaned <> ''
          AND NOT EXISTS (
              SELECT 1 FROM chunks c
              WHERE c.source_type = 'email'
                AND c.strategy    = 'context'
                AND c.source_id   = e.email_id::text
          )
        ORDER BY e.email_id
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        sql += " LIMIT %s"
        params = (limit,)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [
            {
                "email_id": row[0],
                "voyage_key": row[1],
                "thread_id": row[2],
                "body_cleaned": row[3],
                "summary": row[4],
            }
            for row in cur.fetchall()
        ]


def upsert_chunks(conn: psycopg.Connection, rows: Sequence[dict]) -> None:
    """Batch upsert chunk rows. Each row dict must contain:
        source_type, source_id, voyage_key, thread_id, chunk_index,
        text, embedding (halfvec literal str), char_count, strategy, model.
    """
    if not rows:
        return
    with conn.cursor() as cur:
        for r in rows:
            cur.execute(
                """
                INSERT INTO chunks
                    (source_type, source_id, voyage_key, thread_id, chunk_index,
                     text, embedding, char_count, strategy, model)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s::halfvec, %s, %s, %s)
                ON CONFLICT (source_type, source_id, strategy, chunk_index)
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
                    r["model"],
                ),
            )
    conn.commit()
