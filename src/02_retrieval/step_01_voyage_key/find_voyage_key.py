from __future__ import annotations

import psycopg


def find_winning_voyage_keys(
    conn: psycopg.Connection,
    query_embedding: list[float],
    top_k: int = 500,
    source_types: list[str] | None = None,
    strategies: list[str] | None = None,
) -> tuple[list[str], dict[str, int]]:
    """
    Searches chunks for the top_k most similar chunks to query_embedding,
    counts voyage_key appearances, and returns all keys tied for the highest count.

    Returns:
        (winning_keys, all_vote_counts)
        winning_keys: voyage_keys tied for most appearances in the top_k
        all_vote_counts: {voyage_key: count} for every key that appeared
    """
    filters: list[str] = []
    params: list = []
    if source_types is not None:
        filters.append("source_type = ANY(%s)")
        params.append(source_types)
    if strategies is not None:
        filters.append("strategy = ANY(%s)")
        params.append(strategies)
    where_clause = ("WHERE " + " AND ".join(filters)) if filters else ""
    params += [query_embedding, top_k]

    sql = f"""
        WITH ranked AS (
            SELECT voyage_key
            FROM chunks
            {where_clause}
            ORDER BY embedding <=> %s::halfvec
            LIMIT %s
        )
        SELECT voyage_key, COUNT(*)::int AS cnt
        FROM ranked
        GROUP BY voyage_key
        ORDER BY cnt DESC, voyage_key
    """
    conn.execute(f"SET LOCAL hnsw.ef_search = {int(top_k)}")
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return [], {}

    all_counts = {row[0]: row[1] for row in rows}
    max_cnt = rows[0][1]
    winning_keys = [row[0] for row in rows if row[1] == max_cnt]
    return winning_keys, all_counts
