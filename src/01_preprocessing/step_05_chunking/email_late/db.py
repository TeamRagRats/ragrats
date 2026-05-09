from __future__ import annotations

# DB queries for email late chunking: pending threads, thread emails,
# and chunk upserts (with embedding written directly as halfvec).

from typing import Any, Sequence
from uuid import UUID

import psycopg


def get_pending_thread_ids(
    conn: psycopg.Connection, limit: int | None
) -> list[UUID]:
    """Threads that have at least one email not yet late-chunked."""
    sql = """
        SELECT DISTINCT e.thread_id
        FROM emails e
        WHERE e.body_cleaned IS NOT NULL
          AND e.body_cleaned <> ''
          AND e.thread_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM chunks c
              WHERE c.source_type = 'email'
                AND c.strategy    = 'late'
                AND c.source_id   = e.email_id::text
          )
        ORDER BY e.thread_id
    """
    params: tuple[Any, ...] = ()
    if limit is not None:
        sql += " LIMIT %s"
        params = (limit,)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [row[0] for row in cur.fetchall()]


def get_thread_emails(conn: psycopg.Connection, thread_id: UUID) -> list[dict]:
    """All emails in a thread, ordered by sent_at (NULLs last)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT email_id, voyage_key, body_cleaned, sent_at
            FROM emails
            WHERE thread_id = %s
              AND body_cleaned IS NOT NULL
              AND body_cleaned <> ''
            ORDER BY sent_at ASC NULLS LAST, email_id ASC
            """,
            (str(thread_id),),
        )
        return [
            {
                "email_id": row[0],
                "voyage_key": row[1],
                "body_cleaned": row[2],
                "sent_at": row[3],
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
