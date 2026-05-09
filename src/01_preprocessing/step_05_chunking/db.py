from __future__ import annotations

# Shared DB helper for chunking: upserts finished chunks into the chunks table.
# Per-source-type SELECT helpers live in step_05_chunking/sources/.

import psycopg


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
