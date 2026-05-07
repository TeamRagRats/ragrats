from __future__ import annotations

import json
import psycopg

def log_retrieval(
    conn: psycopg.Connection,
    *,
    query_id: str,
    query_text: str,
    source_types: list[str] | None,
    top_k_1: int,
    top_k_2: int,
    winning_keys: list[str],
    key_vote_counts: dict[str, int],
    step1_ms: int,
    step2_ms: int,
    total_ms: int,
    chunks_returned: int,
    chunks: list,
    chunks_expanded_returned: int = 0,
    chunks_expanded: list | None = None,
    query_variants: list[str] | None = None,
) -> None:
    def _serialise(cs: list) -> str:
        return json.dumps([
            {
                "chunk_id": c.chunk_id,
                "voyage_key": c.voyage_key,
                "source_type": c.source_type,
                "source_id": c.source_id,
                "chunk_index": c.chunk_index,
                "similarity": round(c.similarity, 4),
                "text": c.text,
            }
            for c in cs
        ])

    chunks_json = _serialise(chunks)
    chunks_expanded_json = _serialise(chunks_expanded) if chunks_expanded else None

    seen_types: dict[str, None] = {}
    seen_ids: dict[str, None] = {}
    for c in chunks:
        seen_types[c.source_type] = None
        seen_ids[c.source_id] = None
    retrieved_source_types = list(seen_types)
    retrieved_source_ids = list(seen_ids)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO retrieval_logging
                (query_id, query_text, source_types, top_k_1, top_k_2, winning_keys,
                 key_vote_counts, step1_ms, step2_ms, total_ms, chunks_returned, chunks,
                 chunks_expanded_returned, chunks_expanded,
                 retrieved_source_types, retrieved_source_ids, query_variants)
            VALUES (%s::uuid, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s, %s::jsonb)
            """,
            (
                query_id,
                query_text,
                source_types,
                top_k_1,
                top_k_2,
                winning_keys,
                json.dumps(key_vote_counts),
                step1_ms,
                step2_ms,
                total_ms,
                chunks_returned,
                chunks_json,
                chunks_expanded_returned,
                chunks_expanded_json,
                retrieved_source_types,
                retrieved_source_ids,
                json.dumps(query_variants) if query_variants else None,
            ),
        )
    conn.commit()
