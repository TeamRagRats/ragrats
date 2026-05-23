from __future__ import annotations

import psycopg

from ..retrieve_vector import RetrievedChunk


_ALL_BM25_STRATEGIES = ("context", "plain", "late", "summary")


def bm25_retrieve(
    conn: psycopg.Connection,
    query_text: str,
    top_k: int = 20,
    voyage_keys: list[str] | None = None,
    source_types: list[str] | None = None,
    strategies: list[str] | None = None,
) -> list[RetrievedChunk]:
    """Real BM25 lexical retrieval via ParadeDB's pg_search extension.

    Uses paradedb.match() to match `text` against the query and
    `paradedb.score(chunk_id)` to retrieve the true BM25 score (with IDF and
    document-length normalization; Tantivy defaults k1=1.2, b=0.75). Backed
    by the chunks_bm25_idx index from migration 0096.

    paradedb.match() tokenizes the natural-language query internally — the
    raw `text @@@ %s` form treats the right-hand side as Tantivy query syntax
    (column:term pairs) and chokes on parens / special characters that
    appear in real user questions.
    """
    if not query_text or not query_text.strip():
        return []

    effective_strategies = list(strategies) if strategies is not None else list(_ALL_BM25_STRATEGIES)

    # paradedb.match() carries the BM25 match on `text`. The remaining
    # predicates (strategy/voyage_key/source_type) are post-filters on the
    # heap; pushdown into chunks_bm25_idx would require composing them via
    # paradedb.boolean() / paradedb.term(), which we can layer in later if
    # the filter cost becomes a problem.
    where_parts: list[str] = [
        "chunk_id @@@ paradedb.match('text', %s)",
        "strategy = ANY(%s)",
    ]
    where_params: list = [query_text, effective_strategies]
    if voyage_keys is not None:
        where_parts.append("voyage_key = ANY(%s)")
        where_params.append(voyage_keys)
    if source_types is not None:
        where_parts.append("source_type = ANY(%s)")
        where_params.append(source_types)

    sql = f"""
        SELECT chunk_id::text, source_type, source_id, strategy, voyage_key, chunk_index, text,
               paradedb.score(chunk_id) AS score
        FROM chunks
        WHERE {" AND ".join(where_parts)}
        ORDER BY score DESC
        LIMIT %s
    """
    params = where_params + [top_k]
    rows = conn.execute(sql, params).fetchall()
    return [
        RetrievedChunk(
            chunk_id=r[0], source_type=r[1], source_id=r[2], strategy=r[3],
            voyage_key=r[4], chunk_index=r[5], text=r[6], similarity=float(r[7]),
        )
        for r in rows
    ]
