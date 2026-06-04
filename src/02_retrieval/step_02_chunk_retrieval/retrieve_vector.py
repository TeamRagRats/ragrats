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
    chunkers: list[str] | None = None,
    ef_search: int | None = None,
) -> list[RetrievedChunk]:
    """
    Returns the top_k most similar chunks from chunks, optionally filtered to
    specific voyage_keys, source_types, and/or strategies.

    When voyage_keys is None, no voyage_key filter is applied — useful when the
    caller wants to bypass step 1 (voyage_key voting).

    ef_search: HNSW candidate-pool size. Defaults to top_k. Always SET LOCAL
    here so this step does not silently inherit step 1's value (or fall back
    to Postgres' default of 40 when step 1 is skipped).
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
    if chunkers is not None:
        filters.append("chunker = ANY(%s)")
        params.append(chunkers)
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
    effective_ef = int(ef_search) if ef_search is not None else int(top_k)
    conn.execute(f"SET LOCAL hnsw.ef_search = {effective_ef}")
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
