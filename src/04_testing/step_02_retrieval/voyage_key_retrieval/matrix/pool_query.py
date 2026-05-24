"""Hent én kandidat-pool pr. (spørgsmål, strategi) og genbrug den på tværs af k.

I stedet for at køre en HNSW-søgning for hvert k, henter vi de øverste `pool`
chunks én gang med ef_search = pool og udregner hit@k ved at slæbe den ordnede
voyage_key-liste:
  - rank_threshold = None: recall@k = optræder expected_key blandt de første k?
  - rank_threshold = N:    rammer votingen? expected_key skal være blandt de N
    mest-stemte keys blandt de første k chunks (N=1 = den vindende key).
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
    """De `pool` nærmeste chunks' voyage_key, i similaritets-rækkefølge."""
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
    """Rang af expected_key efter stemmetal blandt sliced_keys (None hvis fraværende).

    Samme voting og tiebreak som run_test._compute_rank: sortér på faldende
    stemmetal og brug positionen (dict bevarer similaritets-rækkefølgen).
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
    """Tæller (strategi, k) som et hit for dette spørgsmål?"""
    sliced = ranked_keys[:k]
    if rank_threshold is None:
        return expected_key in sliced
    rank = _expected_vote_rank(sliced, expected_key)
    return rank is not None and rank <= rank_threshold
