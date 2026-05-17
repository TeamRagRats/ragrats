from __future__ import annotations

import psycopg

from step_02_chunk_retrieval.retrieve_chunks import RetrievedChunk

from .tokenize_query import tokenize_query


def bm25_retrieve(
    conn: psycopg.Connection,
    query_text: str,
    top_k: int = 20,
    voyage_keys: list[str] | None = None,
    source_types: list[str] | None = None,
) -> list[RetrievedChunk]:
    """Lexical retrieval against chunks via Postgres ts_rank.

    Hardcoded to strategy='context' — that's the only strategy backed by the
    text_tsv column / partial GIN index from migration 0081. Returns
    RetrievedChunk rows with `similarity` set to the raw ts_rank score so
    callers can introspect; ranking for fusion uses position, not score.
    """
    normalized = tokenize_query(query_text)
    if not normalized:
        return []

    where_parts: list[str] = [
        "strategy = 'context'",
        "text_tsv @@ plainto_tsquery('simple', %s)",
    ]
    where_params: list = [normalized]
    if voyage_keys is not None:
        where_parts.append("voyage_key = ANY(%s)")
        where_params.append(voyage_keys)
    if source_types is not None:
        where_parts.append("source_type = ANY(%s)")
        where_params.append(source_types)

    sql = f"""
        SELECT chunk_id::text, source_type, source_id, strategy, voyage_key, chunk_index, text,
               ts_rank(text_tsv, plainto_tsquery('simple', %s)) AS score
        FROM chunks
        WHERE {" AND ".join(where_parts)}
        ORDER BY score DESC
        LIMIT %s
    """
    params = [normalized] + where_params + [top_k]
    rows = conn.execute(sql, params).fetchall()
    return [
        RetrievedChunk(
            chunk_id=r[0], source_type=r[1], source_id=r[2], strategy=r[3],
            voyage_key=r[4], chunk_index=r[5], text=r[6], similarity=float(r[7]),
        )
        for r in rows
    ]
