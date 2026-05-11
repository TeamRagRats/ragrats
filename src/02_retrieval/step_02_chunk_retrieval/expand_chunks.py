# Small-to-big retrieval — expands each retrieved anchor chunk by fetching its
# neighboring chunks (±window) from the same (source_type, source_id, strategy),
# ordered by chunk_index. Anchor chunks keep their original similarity score;
# neighbors are marked 0.0. Overlapping neighbor ranges from adjacent anchors
# within the same (source_type, source_id, strategy) group are merged.
from __future__ import annotations

from collections import defaultdict

import psycopg

from .retrieve_chunks import RetrievedChunk


def expand_chunks(
    conn: psycopg.Connection,
    chunks: list[RetrievedChunk],
    window: int = 2,
) -> list[RetrievedChunk]:
    if not chunks:
        return []

    anchor_scores: dict[str, float] = {c.chunk_id: c.similarity for c in chunks}

    # Group chunk_indexes by (source_type, source_id, strategy) so neighbours stay
    # within the same embedding variant — without this, a 'late' anchor would pull
    # in 'plain'/'context' rows that share the same source_id.
    grouped: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for c in chunks:
        grouped[(c.source_type, c.source_id, c.strategy)].append(c.chunk_index)

    # Merge overlapping [lo, hi] ranges within each group
    ranges: list[tuple[str, str, str, int, int]] = []
    for (source_type, source_id, strategy), indices in grouped.items():
        intervals = sorted((i - window, i + window) for i in indices)
        lo, hi = intervals[0]
        for next_lo, next_hi in intervals[1:]:
            if next_lo <= hi + 1:
                hi = max(hi, next_hi)
            else:
                ranges.append((source_type, source_id, strategy, lo, hi))
                lo, hi = next_lo, next_hi
        ranges.append((source_type, source_id, strategy, lo, hi))

    values_sql = ", ".join(["(%s, %s, %s, %s, %s)"] * len(ranges))
    params: list = []
    for source_type, source_id, strategy, lo, hi in ranges:
        params += [source_type, source_id, strategy, lo, hi]

    sql = f"""
        SELECT c.chunk_id::text, c.source_type, c.source_id, c.strategy, c.voyage_key,
               c.chunk_index, c.text
        FROM chunks c
        JOIN (VALUES {values_sql}) AS r(source_type, source_id, strategy, lo, hi)
          ON c.source_type = r.source_type
         AND c.source_id = r.source_id
         AND c.strategy = r.strategy
         AND c.chunk_index BETWEEN r.lo AND r.hi
        ORDER BY c.source_type, c.source_id, c.strategy, c.chunk_index
    """
    rows = conn.execute(sql, params).fetchall()

    return [
        RetrievedChunk(
            chunk_id=row[0],
            source_type=row[1],
            source_id=row[2],
            strategy=row[3],
            voyage_key=row[4],
            chunk_index=row[5],
            text=row[6],
            similarity=anchor_scores.get(row[0], 0.0),
        )
        for row in rows
    ]
