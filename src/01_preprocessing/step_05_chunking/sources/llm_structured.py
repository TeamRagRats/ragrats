from __future__ import annotations

# Chunking source: llm_structured
# Reads LLM-structured markdown (mode='full') for each attachment and chunks it
# with the 'late' strategy. Same sha256 may appear under multiple voyage_keys
# (generic forms attached to many emails) — we duplicate one chunk-row per
# (sha256, voyage_key) so retrieval filtered on voyage_key still matches.

import logging
from typing import Optional

import psycopg
from psycopg.rows import dict_row

from step_05_chunking.helpers import chunk_late_and_upsert

SOURCE_TYPE = "llm_structured"
STRATEGY = "late"


def get_pending(conn: psycopg.Connection) -> list[dict]:
    """One row per (sha256, voyage_key) where mode='full' and not yet chunked."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT DISTINCT ls.sha256, a.voyage_key, ls.structured_md
            FROM llm_structured ls
            JOIN attachments a ON a.sha256 = ls.sha256
            WHERE ls.mode = 'full'
              AND ls.structured_md IS NOT NULL
              AND ls.structured_md <> ''
              AND NOT EXISTS (
                  SELECT 1 FROM chunks c
                  WHERE c.source_type = %s
                    AND c.source_id = ls.sha256|| '__' || a.voyage_key
                    AND c.strategy = %s
              )
            """,
            (SOURCE_TYPE, STRATEGY),
        )
        return cur.fetchall()


def run(
    conn: psycopg.Connection,
    tokenizer,
    run_id,
    logger: logging.Logger,
    limit: Optional[int] = None,
) -> int:
    rows = get_pending(conn)
    if limit is not None:
        rows = rows[:limit]
    logger.info(f"[chunk] {len(rows)} llm_structured (sha256, voyage) afventer chunking")

    done = 0
    for row in rows:
        source_id = f"{row['sha256']}__{row['voyage_key']}"
        done += chunk_late_and_upsert(
            conn,
            source_type=SOURCE_TYPE,
            source_id=source_id,
            voyage_key=row["voyage_key"],
            summary=row["structured_md"],
            tokenizer=tokenizer,
            run_id=run_id,
            label=f"llm_structured {row['sha256'][:12]}…/{row['voyage_key']}",
            logger=logger,
        )
    logger.info(f"[chunk] llm_structured færdige: {done} chunks indsat")
    return done
