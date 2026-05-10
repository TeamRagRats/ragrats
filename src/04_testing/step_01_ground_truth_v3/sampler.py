from __future__ import annotations

import re
from dataclasses import dataclass

import psycopg

_TRAILING_NUM = re.compile(r"^(.+)_(\d+)$")


def vessel_name_from_key(voyage_key: str) -> str:
    m = _TRAILING_NUM.match(voyage_key)
    base = m.group(1) if m else voyage_key
    return base.replace("_", " ").title()


def list_voyage_keys(conn: psycopg.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT voyage_key FROM chunks ORDER BY voyage_key"
    ).fetchall()
    return [r[0] for r in rows]


@dataclass
class ChunkRow:
    chunk_id: str
    source_type: str
    source_id: str
    chunk_index: int
    voyage_key: str
    vessel_name: str
    text: str


def sample_chunks(
    conn: psycopg.Connection,
    voyage_key: str,
    limit: int,
) -> list[ChunkRow]:
    """Sample plain chunks (emails + attachments) for a voyage, stratified by source_type."""
    rows = conn.execute(
        """
        WITH ranked AS (
            SELECT
                chunk_id,
                source_type,
                source_id,
                chunk_index,
                voyage_key,
                text,
                ROW_NUMBER() OVER (
                    PARTITION BY source_type
                    ORDER BY random()
                ) AS rn
            FROM chunks
            WHERE strategy    = 'plain'
              AND voyage_key  = %s
              AND text IS NOT NULL
              AND text <> ''
        )
        SELECT chunk_id, source_type, source_id, chunk_index, voyage_key, text
        FROM ranked
        ORDER BY random()
        LIMIT %s
        """,
        (voyage_key, limit),
    ).fetchall()

    vessel_name = vessel_name_from_key(voyage_key)
    return [
        ChunkRow(
            chunk_id=str(r[0]),
            source_type=r[1],
            source_id=str(r[2]),
            chunk_index=r[3],
            voyage_key=r[4],
            vessel_name=vessel_name,
            text=r[5] or "",
        )
        for r in rows
    ]
