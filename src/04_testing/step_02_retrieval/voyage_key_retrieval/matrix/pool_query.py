"""Fetch one candidate pool per (question, strategy) and reuse it across k.

Instead of running an HNSW search for each k, we fetch the top `pool` chunks
once with ef_search = pool and compute hit@k by slicing the ordered
voyage_key list:
  - rank_threshold = None: recall@k = does expected_key appear among the first k?
  - rank_threshold = N:    does it pass the voting? expected_key must be among the
    N most-voted keys among the first k chunks (N=1 = the winning key).
"""

from __future__ import annotations

import psycopg


def ranked_voyage_keys(
    conn: psycopg.Connection,
    query_embedding: list[float],
    pool: int,
    source_types: list[str] | None,
    strategy: str,
) -> list[str]:
    """The voyage_key of the `pool` nearest chunks, in similarity order."""
    filters = ["strategy = %s"]
    params: list = [strategy]
    if source_types is not None:
        filters.append("source_type = ANY(%s)")
        params.append(source_types)
    where_clause = "WHERE " + " AND ".join(filters)
    params += [query_embedding, pool]

    sql = f"""
        SELECT voyage_key
        FROM chunks
        {where_clause}
        ORDER BY embedding <=> %s::halfvec
        LIMIT %s
    """
    conn.execute(f"SET LOCAL hnsw.ef_search = {int(pool)}")
    rows = conn.execute(sql, params).fetchall()
    return [r[0] for r in rows]


def _expected_vote_rank(sliced_keys: list[str], expected_key: str) -> int | None:
    """Rank of expected_key by vote count among sliced_keys (None if absent).

    Same voting and tiebreak as run_test._compute_rank: sort by descending
    vote count and use the position (dict preserves the similarity order).
    """
    counts: dict[str, int] = {}
    for key in sliced_keys:
        counts[key] = counts.get(key, 0) + 1
    if expected_key not in counts:
        return None
    sorted_keys = sorted(counts, key=lambda k: -counts[k])
    return sorted_keys.index(expected_key) + 1


def hit_at_k(
    ranked_keys: list[str],
    expected_key: str,
    k: int,
    rank_threshold: int | None,
) -> bool:
    """Does (strategy, k) count as a hit for this question?"""
    sliced = ranked_keys[:k]
    if rank_threshold is None:
        return expected_key in sliced
    rank = _expected_vote_rank(sliced, expected_key)
    return rank is not None and rank <= rank_threshold
