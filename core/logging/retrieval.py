from __future__ import annotations

import json
from uuid import UUID
import psycopg

def log_retrieval(
    conn: psycopg.Connection,
    *,
    query: str,
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
) -> str:
    """Logs a retrieval run to the database and returns the run_id."""
    chunks_json = json.dumps([
        {
            "chunk_id": c.chunk_id,
            "voyage_key": c.voyage_key,
            "source_type": c.source_type,
            "source_id": c.source_id,
            "chunk_index": c.chunk_index,
            "similarity": round(c.similarity, 4),
            "text": c.text,
        }
        for c in chunks
    ])
    
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO retrieval_logging
                (query, source_types, top_k_1, top_k_2, winning_keys, key_vote_counts,
                 step1_ms, step2_ms, total_ms, chunks_returned, chunks)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb)
            RETURNING run_id
            """,
            (
                query,
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
            ),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return str(run_id)
