# Small-to-big retrieval — expands each retrieved anchor chunk by fetching its
# neighboring chunks (±window) from the same source, ordered by chunk_index.
# Anchor chunks keep their original similarity score; neighbors are marked 0.0.
# Overlapping neighbor ranges from adjacent anchors are merged into one block.
from __future__ import annotations

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

    # Build (source_id → list of chunk_index) map, then merge into contiguous ranges
    from collections import defaultdict
    source_indices: dict[str, list[int]] = defaultdict(list)
    for c in chunks:
        source_indices[c.source_id].append(c.chunk_index)

    # Merge overlapping [lo, hi] ranges per source
    ranges: list[tuple[str, int, int]] = []
    for source_id, indices in source_indices.items():
        intervals = sorted((i - window, i + window) for i in indices)
        lo, hi = intervals[0]
        for next_lo, next_hi in intervals[1:]:
            if next_lo <= hi + 1:
                hi = max(hi, next_hi)
            else:
                ranges.append((source_id, lo, hi))
                lo, hi = next_lo, next_hi
        ranges.append((source_id, lo, hi))

    # Single query for all ranges using a VALUES table
    values_sql = ", ".join(["(%s, %s, %s)"] * len(ranges))
    params: list = []
    for source_id, lo, hi in ranges:
        params += [source_id, lo, hi]

    sql = f"""
        SELECT c.chunk_id::text, c.source_type, c.source_id, c.voyage_key,
               c.chunk_index, c.text
        FROM chunks c
        JOIN (VALUES {values_sql}) AS r(source_id, lo, hi)
          ON c.source_id = r.source_id
         AND c.chunk_index BETWEEN r.lo AND r.hi
        ORDER BY c.source_id, c.chunk_index
    """
    rows = conn.execute(sql, params).fetchall()

    return [
        RetrievedChunk(
            chunk_id=row[0],
            source_type=row[1],
            source_id=row[2],
            voyage_key=row[3],
            chunk_index=row[4],
            text=row[5],
            similarity=anchor_scores.get(row[0], 0.0),
        )
        for row in rows
    ]
