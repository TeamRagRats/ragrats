from __future__ import annotations

import psycopg


def find_winning_voyage_keys(
    conn: psycopg.Connection,
    query_embedding: list[float],
    top_k: int = 500,
    top_n_keys: int = 10,
    source_types: list[str] | None = None,
) -> tuple[list[str], dict[str, float]]:
    """
    Searches chunks for the top_k most similar chunks to query_embedding,
    scores each voyage_key by summing (1 - distance) across its chunks,
    and returns the top_n_keys by score.

    Similarity-weighted scoring reduces length bias: a voyage with many
    mediocre chunks no longer outcompetes one with fewer highly relevant chunks.

    Returns:
        (winning_keys, all_scores)
        winning_keys: top_n_keys voyage_keys ranked by similarity score
        all_scores: {voyage_key: score} for every key that appeared
    """
    if source_types is not None:
        where_clause = "WHERE source_type = ANY(%s)"
        params: list = [source_types, query_embedding, top_k]
    else:
        where_clause = ""
        params = [query_embedding, top_k]

    sql = f"""
        WITH ranked AS (
            SELECT voyage_key,
                   embedding <=> %s::halfvec AS distance
            FROM chunks
            {where_clause}
            ORDER BY distance
            LIMIT %s
        )
        SELECT voyage_key, SUM(1 - distance)::float AS score
        FROM ranked
        GROUP BY voyage_key
        ORDER BY score DESC, voyage_key
    """
    conn.execute(f"SET LOCAL hnsw.ef_search = {int(top_k)}")
    rows = conn.execute(sql, params).fetchall()
    if not rows:
        return [], {}

    all_scores = {row[0]: row[1] for row in rows}
    winning_keys = [row[0] for row in rows[:top_n_keys]]
    return winning_keys, all_scores
