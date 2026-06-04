from __future__ import annotations

import psycopg

from ..retrieve_vector import RetrievedChunk

from .tokenize_query import tokenize_query


_ALL_TSRANK_STRATEGIES = ("context", "plain", "late", "summary")


def tsrank_retrieve(
    conn: psycopg.Connection,
    query_text: str,
    top_k: int = 20,
    voyage_keys: list[str] | None = None,
    source_types: list[str] | None = None,
    strategies: list[str] | None = None,
    chunkers: list[str] | None = None,
) -> list[RetrievedChunk]:
    """Lexical retrieval against chunks via Postgres ts_rank.

    Despite its historical name, this is NOT BM25 — it's Postgres' built-in
    ts_rank, a TF-IDF-style cover-density score over a tsvector GIN index.
    Kept around as the legacy lexical signal for A/B comparison against the
    pg_search-backed bm25_retrieve() in the sibling bm25/ folder.

    Queries all strategies that have a populated text_tsv (context, plain,
    late, summary — backed by migration 0086). Pass `strategies` to restrict
    to a subset. Returns RetrievedChunk rows with `similarity` set to the raw
    ts_rank score; ranking for fusion uses position, not score.
    """
    normalized = tokenize_query(query_text)
    if not normalized:
        return []

    # Build an OR tsquery so any matching term scores a hit. plainto_tsquery
    # AND-s all words, making full-sentence queries match nothing.
    tokens = [t for t in normalized.split() if len(t) > 1]
    if not tokens:
        return []
    tsquery_str = " | ".join(tokens)

    effective_strategies = list(strategies) if strategies is not None else list(_ALL_TSRANK_STRATEGIES)

    where_parts: list[str] = [
        "strategy = ANY(%s)",
        "text_tsv @@ to_tsquery('simple', %s)",
    ]
    where_params: list = [effective_strategies, tsquery_str]
    if voyage_keys is not None:
        where_parts.append("voyage_key = ANY(%s)")
        where_params.append(voyage_keys)
    if source_types is not None:
        where_parts.append("source_type = ANY(%s)")
        where_params.append(source_types)
    if chunkers is not None:
        where_parts.append("chunker = ANY(%s)")
        where_params.append(chunkers)

    sql = f"""
        SELECT chunk_id::text, source_type, source_id, strategy, voyage_key, chunk_index, text,
               ts_rank(text_tsv, to_tsquery('simple', %s)) AS score
        FROM chunks
        WHERE {" AND ".join(where_parts)}
        ORDER BY score DESC
        LIMIT %s
    """
    params = [tsquery_str] + where_params + [top_k]
    rows = conn.execute(sql, params).fetchall()
    return [
        RetrievedChunk(
            chunk_id=r[0], source_type=r[1], source_id=r[2], strategy=r[3],
            voyage_key=r[4], chunk_index=r[5], text=r[6], similarity=float(r[7]),
        )
        for r in rows
    ]
