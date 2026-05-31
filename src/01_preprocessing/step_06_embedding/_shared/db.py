from __future__ import annotations

# Shared chunk upsert used by every embedding strategy. Writes the embedding as
# a Postgres halfvec and dedups on (source_type, source_id, strategy, chunk_index).

from typing import Sequence

import psycopg


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
