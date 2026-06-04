from __future__ import annotations

import psycopg


def find_winning_voyage_keys(
    conn: psycopg.Connection,
    query_embedding: list[float],
    top_k: int = 500,
    source_types: list[str] | None = None,
    strategies: list[str] | None = None,
    chunkers: list[str] | None = None,
    ef_search: int | None = None,
    return_candidates: bool = False,
):
    """
    Searches chunks for the top_k most similar chunks to query_embedding,
    counts voyage_key appearances, and returns all keys tied for the highest count.

    Returns:
        (winning_keys, all_vote_counts) by default, or
        (winning_keys, all_vote_counts, candidates) when return_candidates=True.
        winning_keys: voyage_keys tied for most appearances in the top_k
        all_vote_counts: {voyage_key: count} for every key that appeared
        candidates: per-chunk metadata for the top_k (rank, chunk_id, source_id,
                    source_type, strategy, voyage_key, similarity) — for logging.

    ef_search: HNSW candidate-pool size for this step. Defaults to top_k
    (pgvector requires ef_search >= LIMIT). Raise above top_k to trade
    latency for recall.
    """
    if return_candidates:
        return _find_with_candidates(
            conn, query_embedding, top_k, source_types, strategies, chunkers, ef_search
        )

    filters: list[str] = []
    filter_params: list = []
    if source_types is not None:
        filters.append("source_type = ANY(%s)")
        filter_params.append(source_types)
    if strategies is not None:
        filters.append("strategy = ANY(%s)")
        filter_params.append(strategies)
    if chunkers is not None:
        filters.append("chunker = ANY(%s)")
        filter_params.append(chunkers)
    where_clause = ("WHERE " + " AND ".join(filters)) if filters else ""
    params = [query_embedding] + filter_params + [query_embedding, top_k]

    # Ties (same vote count) are broken by similarity — the key whose best chunk
    # lies nearest the query wins (MIN(dist)). Matches the matrix harness's
    # tiebreak; previously we broke alphabetically on voyage_key, which was arbitrary.
    sql = f"""
        WITH ranked AS (
            SELECT voyage_key, embedding <=> %s::halfvec AS dist
            FROM chunks
            {where_clause}
            ORDER BY embedding <=> %s::halfvec
            LIMIT %s
        )
        SELECT voyage_key, COUNT(*)::int AS cnt
        FROM ranked
        GROUP BY voyage_key
        ORDER BY cnt DESC, MIN(dist) ASC
    """
    effective_ef = int(ef_search) if ef_search is not None else int(top_k)
    conn.execute(f"SET LOCAL hnsw.ef_search = {effective_ef}")
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return [], {}

    all_counts = {row[0]: row[1] for row in rows}
    max_cnt = rows[0][1]
    winning_keys = [row[0] for row in rows if row[1] == max_cnt]
    return winning_keys, all_counts


def _find_with_candidates(
    conn: psycopg.Connection,
    query_embedding: list[float],
    top_k: int,
    source_types: list[str] | None,
    strategies: list[str] | None,
    chunkers: list[str] | None,
    ef_search: int | None,
) -> tuple[list[str], dict[str, int], list[dict]]:
    """Same voting as find_winning_voyage_keys, but materializes the top_k
    candidate chunks and aggregates vote_counts in Python so the candidates
    can be logged. Used only by the test harness (return_candidates=True)."""
    filters: list[str] = []
    filter_params: list = []
    if source_types is not None:
        filters.append("source_type = ANY(%s)")
        filter_params.append(source_types)
    if strategies is not None:
        filters.append("strategy = ANY(%s)")
        filter_params.append(strategies)
    if chunkers is not None:
        filters.append("chunker = ANY(%s)")
        filter_params.append(chunkers)
    where_clause = ("WHERE " + " AND ".join(filters)) if filters else ""
    params = [query_embedding] + filter_params + [query_embedding, top_k]

    sql = f"""
        SELECT chunk_id::text, source_type, source_id::text, strategy, voyage_key,
               1 - (embedding <=> %s::halfvec) AS similarity
        FROM chunks
        {where_clause}
        ORDER BY embedding <=> %s::halfvec
        LIMIT %s
    """
    effective_ef = int(ef_search) if ef_search is not None else int(top_k)
    conn.execute(f"SET LOCAL hnsw.ef_search = {effective_ef}")
    rows = conn.execute(sql, params).fetchall()

    candidates: list[dict] = []
    counts: dict[str, int] = {}
    for rank, (chunk_id, source_type, source_id, strategy, voyage_key, sim) in enumerate(rows, 1):
        candidates.append({
            "rank": rank,
            "chunk_id": chunk_id,
            "source_id": source_id,
            "source_type": source_type,
            "strategy": strategy,
            "voyage_key": voyage_key,
            "similarity": float(sim),
        })
        counts[voyage_key] = counts.get(voyage_key, 0) + 1

    if not counts:
        return [], {}, []

    # counts is built in similarity order (rows sorted by dist), and sorted is
    # stable — so ties preserve similarity order instead of breaking alphabetically
    # on voyage_key. Matches find_winning_voyage_keys and the matrix harness.
    all_counts = dict(sorted(counts.items(), key=lambda kv: -kv[1]))
    max_cnt = max(all_counts.values())
    winning_keys = [k for k, c in all_counts.items() if c == max_cnt]
    return winning_keys, all_counts, candidates
