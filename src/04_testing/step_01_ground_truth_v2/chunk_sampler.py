"""
Stratified chunk sampling for one voyage.

Samples up to MAX_CHUNKS_PER_SOURCE_TYPE chunks per source_type within
a voyage, then shuffles and returns up to `limit` rows.
"""
from __future__ import annotations

from dataclasses import dataclass

import psycopg

from config import MAX_CHUNKS_PER_SOURCE_TYPE


@dataclass
class ChunkRow:
    chunk_id: str
    source_type: str
    source_id: str
    voyage_key: str
    text: str


def sample_chunks(
    conn: psycopg.Connection,
    voyage_key: str,
    limit: int,
) -> list[ChunkRow]:
    rows = conn.execute(
        """
        WITH ranked AS (
            SELECT
                chunk_id,
                source_type,
                source_id,
                voyage_key,
                text,
                ROW_NUMBER() OVER (
                    PARTITION BY source_type
                    ORDER BY random()
                ) AS rn
            FROM chunks
            WHERE voyage_key = %s
        )
        SELECT chunk_id, source_type, source_id, voyage_key, text
        FROM ranked
        WHERE rn <= %s
        ORDER BY random()
        LIMIT %s
        """,
        (voyage_key, MAX_CHUNKS_PER_SOURCE_TYPE, limit),
    ).fetchall()

    return [
        ChunkRow(
            chunk_id=str(r[0]),
            source_type=r[1],
            source_id=str(r[2]) if r[2] else "",
            voyage_key=r[3],
            text=r[4] or "",
        )
        for r in rows
    ]
