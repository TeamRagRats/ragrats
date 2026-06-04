from __future__ import annotations

# DB queries for attachment late chunking: pending sha256s, attachment data,
# and chunk upserts (embedding written as halfvec).

from typing import Any, Sequence

import psycopg


def get_pending_sha256s(
    conn: psycopg.Connection,
    chunker: str,
    voyage: str | None = None,
    limit: int | None = None,
) -> list[str]:
    """llm_structured rows not yet late-chunked as attachments with this chunker."""
    parts = [
        """
        SELECT DISTINCT ls.sha256
        FROM llm_structured ls
        JOIN attachments a ON a.sha256 = ls.sha256
        WHERE ls.structured_md IS NOT NULL
          AND ls.structured_md <> ''
          AND NOT EXISTS (
              SELECT 1 FROM chunks c
              WHERE c.source_type = 'attachment'
                AND c.strategy    = 'late'
                AND c.chunker     = %s
                AND c.source_id   = ls.sha256
          )
        """
    ]
    params: list[Any] = [chunker]

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


def get_attachment_data(conn: psycopg.Connection, sha256: str) -> dict | None:
    """Return structured_md, email_summary (nullable), voyage_key, thread_id for one attachment."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ls.structured_md,
                   es.summary        AS email_summary,
                   a.voyage_key,
                   e.thread_id
            FROM   llm_structured ls
            JOIN   attachments    a  ON a.sha256    = ls.sha256
            LEFT JOIN emails      e  ON e.email_id  = a.email_id
            LEFT JOIN email_summaries es ON es.email_id = a.email_id
            WHERE  ls.sha256 = %s
            LIMIT  1
            """,
            (sha256,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {
        "structured_md": row[0],
        "email_summary": row[1],
        "voyage_key":    row[2],
        "thread_id":     row[3],
    }


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
