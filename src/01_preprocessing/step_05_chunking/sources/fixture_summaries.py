from __future__ import annotations

# Chunking source: fixture_summaries
# Reads pending fixture summaries (one per voyage) and chunks them with the 'late' strategy.

import logging
from typing import Optional

import psycopg
from psycopg.rows import dict_row

from step_05_chunking.helpers import chunk_late_and_upsert

SOURCE_TYPE = "fixture_summaries"
STRATEGY = "late"


def get_pending(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT fs.voyage_key, fs.summary
            FROM fixture_summaries fs
            WHERE fs.status = 'ok'
              AND fs.summary IS NOT NULL
              AND fs.summary <> ''
              AND NOT EXISTS (
                  SELECT 1 FROM chunks c
                  WHERE c.source_type = %s
                    AND c.source_id = fs.voyage_key
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
    logger.info(f"[chunk] {len(rows)} fixture(s) afventer chunking")

    done = 0
    for row in rows:
        done += chunk_late_and_upsert(
            conn,
            source_type=SOURCE_TYPE,
            source_id=row["voyage_key"],
            voyage_key=row["voyage_key"],
            summary=row["summary"],
            tokenizer=tokenizer,
            run_id=run_id,
            label=f"fixture {row['voyage_key']}",
            logger=logger,
        )
    logger.info(f"[chunk] Fixtures færdige: {done} chunks indsat")
    return done
