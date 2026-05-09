from __future__ import annotations

# Chunking source: email_summaries
# Reads pending email summaries and chunks them with the 'late' strategy.

import logging
from typing import Optional

import psycopg
from psycopg.rows import dict_row

from step_05_chunking.helpers import chunk_late_and_upsert

SOURCE_TYPE = "email_summaries"
STRATEGY = "late"


def get_pending(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT eas.email_id, eas.voyage_key, eas.summary
            FROM email_attach_summaries eas
            WHERE eas.status = 'ok'
              AND eas.summary IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM chunks c
                  WHERE c.source_type = %s
                    AND c.source_id = eas.email_id::text
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
    logger.info(f"[chunk] {len(rows)} email(s) afventer chunking")

    done = 0
    for row in rows:
        done += chunk_late_and_upsert(
            conn,
            source_type=SOURCE_TYPE,
            source_id=str(row["email_id"]),
            voyage_key=row["voyage_key"],
            summary=row["summary"],
            tokenizer=tokenizer,
            run_id=run_id,
            label=f"email {row['email_id']}",
            logger=logger,
        )
    logger.info(f"[chunk] Emails færdige: {done} chunks indsat")
    return done
