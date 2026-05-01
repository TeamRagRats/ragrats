from __future__ import annotations

from dataclasses import dataclass

import psycopg


@dataclass
class RetrievedChunk:
    chunk_id: str
    source_type: str
    source_id: str
    voyage_key: str
    chunk_index: int
    text: str
    similarity: float


def retrieve_chunks(
    conn: psycopg.Connection,
    query_embedding: list[float],
    voyage_keys: list[str],
    top_k: int = 20,
    source_types: list[str] | None = None,
) -> list[RetrievedChunk]:
    """
    Returns the top_k most similar chunks from chunks, filtered to the given
    voyage_keys and optionally restricted to specific source_types.
    """
    if source_types is not None:
        source_filter = "AND source_type = ANY(%s)"
        params: list = [query_embedding, voyage_keys, source_types, top_k]
    else:
        source_filter = ""
        params = [query_embedding, voyage_keys, top_k]

    sql = f"""
        WITH candidates AS (
            SELECT chunk_id::text, source_type, source_id, voyage_key, chunk_index, text,
                   embedding <=> %s::halfvec AS distance
            FROM chunks
            WHERE voyage_key = ANY(%s)
              {source_filter}
        )
        SELECT chunk_id, source_type, source_id, voyage_key, chunk_index, text,
               1 - distance AS similarity
        FROM candidates
        ORDER BY distance
        LIMIT %s
    """
    rows = conn.execute(sql, params).fetchall()
    return [
        RetrievedChunk(
            chunk_id=row[0],
            source_type=row[1],
            source_id=row[2],
            voyage_key=row[3],
            chunk_index=row[4],
            text=row[5],
            similarity=float(row[6]),
        )
        for row in rows
    ]
