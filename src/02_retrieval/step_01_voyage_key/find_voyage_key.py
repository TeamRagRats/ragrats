from __future__ import annotations

import psycopg


def find_winning_voyage_keys(
    conn: psycopg.Connection,
    query_embedding: list[float],
    top_k: int = 500,
    top_n_keys: int = 5,
    source_types: list[str] | None = None,
) -> tuple[list[str], dict[str, int]]:
    """
    Searches chunks for the top_k most similar chunks to query_embedding,
    counts voyage_key appearances, and returns the top_n_keys by vote count.

    Returns:
        (winning_keys, all_vote_counts)
        winning_keys: top_n_keys voyage_keys ranked by vote count
        all_vote_counts: {voyage_key: count} for every key that appeared
    """
    if source_types is not None:
        where_clause = "WHERE source_type = ANY(%s)"
        params: list = [source_types, query_embedding, top_k]
    else:
        where_clause = ""
        params = [query_embedding, top_k]

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
    winning_keys = [row[0] for row in rows[:top_n_keys]]
    return winning_keys, all_counts
