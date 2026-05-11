from __future__ import annotations

from dataclasses import dataclass

import psycopg


@dataclass
class RetrievedChunk:
    chunk_id: str
    source_type: str
    source_id: str
    strategy: str
    voyage_key: str
    chunk_index: int
    text: str
    similarity: float


def retrieve_chunks(
    conn: psycopg.Connection,
    query_embedding: list[float],
    voyage_keys: list[str] | None = None,
    top_k: int = 20,
    source_types: list[str] | None = None,
    strategies: list[str] | None = None,
) -> list[RetrievedChunk]:
    """
    Returns the top_k most similar chunks from chunks, optionally filtered to
    specific voyage_keys, source_types, and/or strategies.

    When voyage_keys is None, no voyage_key filter is applied — useful when the
    caller wants to bypass step 1 (voyage_key voting).
    """
    filters: list[str] = []
    params: list = [query_embedding]
    if voyage_keys is not None:
        filters.append("voyage_key = ANY(%s)")
        params.append(voyage_keys)
    if source_types is not None:
        filters.append("source_type = ANY(%s)")
        params.append(source_types)
    if strategies is not None:
        filters.append("strategy = ANY(%s)")
        params.append(strategies)
    where_clause = ("WHERE " + " AND ".join(filters)) if filters else ""
    params.append(top_k)

    sql = f"""
        WITH candidates AS (
            SELECT chunk_id::text, source_type, source_id, strategy, voyage_key, chunk_index, text,
                   embedding <=> %s::halfvec AS distance
            FROM chunks
            {where_clause}
        )
        SELECT chunk_id, source_type, source_id, strategy, voyage_key, chunk_index, text,
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
            strategy=row[3],
            voyage_key=row[4],
            chunk_index=row[5],
            text=row[6],
            similarity=float(row[7]),
        )
        for row in rows
    ]
