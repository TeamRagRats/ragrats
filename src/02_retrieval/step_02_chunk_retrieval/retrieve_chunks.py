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
    top_k: int = 100,
    query_text: str | None = None,
    source_types: list[str] | None = None,
) -> list[RetrievedChunk]:
    """
    Returns the top_k most relevant chunks from chunks, filtered to the given voyage_keys.

    When query_text is provided, uses hybrid search: Reciprocal Rank Fusion (RRF) over
    vector similarity and full-text search. Otherwise falls back to pure vector search.
    The candidate set is already small (filtered by voyage_key), so on-the-fly tsvector
    computation is fast without needing a separate index.
    """
    if source_types is not None:
        source_filter = "AND source_type = ANY(%s)"
    else:
        source_filter = ""

    if query_text is not None:
        if source_types is not None:
            vector_params: list = [query_embedding, voyage_keys, source_types]
            text_params: list = [query_text, voyage_keys, source_types]
        else:
            vector_params = [query_embedding, voyage_keys]
            text_params = [query_text, voyage_keys]

        sql = f"""
            WITH
            vector_ranked AS (
                SELECT chunk_id,
                       ROW_NUMBER() OVER (ORDER BY embedding <=> %s::halfvec) AS rank
                FROM chunks
                WHERE voyage_key = ANY(%s)
                  {source_filter}
            ),
            text_ranked AS (
                SELECT c.chunk_id,
                       ROW_NUMBER() OVER (
                           ORDER BY ts_rank(to_tsvector('english', c.text), q.query) DESC
                       ) AS rank
                FROM chunks c, plainto_tsquery('english', %s) AS q(query)
                WHERE c.voyage_key = ANY(%s)
                  {source_filter}
                  AND to_tsvector('english', c.text) @@ q.query
            ),
            combined AS (
                SELECT
                    COALESCE(v.chunk_id, t.chunk_id) AS chunk_id,
                    COALESCE(1.0 / (60.0 + v.rank), 0.0)
                        + COALESCE(1.0 / (60.0 + t.rank), 0.0) AS rrf_score
                FROM vector_ranked v
                FULL OUTER JOIN text_ranked t ON v.chunk_id = t.chunk_id
            )
            SELECT c.chunk_id::text, c.source_type, c.source_id, c.voyage_key,
                   c.chunk_index, c.text, combined.rrf_score
            FROM combined
            JOIN chunks c ON c.chunk_id = combined.chunk_id
            ORDER BY combined.rrf_score DESC
            LIMIT %s
        """
        params = vector_params + text_params + [top_k]
    else:
        if source_types is not None:
            params = [query_embedding, voyage_keys, source_types, top_k]
        else:
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
