from __future__ import annotations

# Chunking source: phase
# Reads pending phase summaries grouped by voyage and chunks them with the
# 'late_overlap' strategy that keeps adjacent phases context-linked.

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import psycopg
from psycopg.rows import dict_row

from log.log_chunking import log_chunking_pending, log_chunking_finished

from step_05_chunking.db import upsert_chunks
from step_05_chunking.late_overlap.chunker import build_overlap_chunks

SOURCE_TYPE = "phase"
STRATEGY = "late_overlap"


def get_pending(conn: psycopg.Connection) -> dict[str, list[dict]]:
    """Return phases grouped by voyage_key, sorted by phase_index ASC.
    Only returns voyages where at least one phase lacks a late_overlap chunk."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT ps.voyage_key, ps.phase_index, ps.summary
            FROM phase_summaries ps
            WHERE ps.status = 'ok'
              AND ps.summary IS NOT NULL
              AND ps.voyage_key IN (
                  SELECT DISTINCT ps2.voyage_key
                  FROM phase_summaries ps2
                  WHERE ps2.status = 'ok'
                    AND NOT EXISTS (
                        SELECT 1 FROM chunks c
                        WHERE c.source_type = %s
                          AND c.source_id = ps2.voyage_key || '__' || ps2.phase_index
                          AND c.strategy = %s
                    )
              )
            ORDER BY ps.voyage_key, ps.phase_index ASC
            """,
            (SOURCE_TYPE, STRATEGY),
        )
        rows = cur.fetchall()

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["voyage_key"], []).append(row)
    return grouped


def run(
    conn: psycopg.Connection,
    tokenizer,  # unused (overlap strategy ignores tokenizer)
    run_id,
    logger: logging.Logger,
    limit: Optional[int] = None,
) -> int:
    grouped = get_pending(conn)
    voyage_keys = list(grouped.keys())
    if limit is not None:
        voyage_keys = voyage_keys[:limit]
    logger.info(f"[chunk] {len(voyage_keys)} voyage(r) med phases afventer chunking")

    done = 0
    for voyage_key in voyage_keys:
        phases = grouped[voyage_key]
        started_at = datetime.now(timezone.utc)
        t0 = time.monotonic()
        try:
            chunks = build_overlap_chunks(phases)
            n = 0
            for chunk in chunks:
                source_id = f"{voyage_key}__{chunk['chunk_index']}"
                log_chunking_pending(conn, SOURCE_TYPE, source_id, voyage_key, started_at, run_id)
                inserted = upsert_chunks(
                    conn, SOURCE_TYPE, source_id, voyage_key, STRATEGY, [chunk],
                )
                log_chunking_finished(
                    conn, SOURCE_TYPE, source_id,
                    finished_at=datetime.now(timezone.utc),
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    status="ok", n_chunks=inserted, char_count=chunk["char_count"],
                )
                n += inserted
            done += n
            logger.debug(f"  [chunk] phases {voyage_key}: {n} chunks indsat")
        except Exception as exc:
            log_chunking_finished(
                conn, SOURCE_TYPE, voyage_key,
                finished_at=datetime.now(timezone.utc),
                duration_ms=int((time.monotonic() - t0) * 1000),
                status="error", error_message=f"{type(exc).__name__}: {exc}",
            )
            raise
    logger.info(f"[chunk] Phases færdige: {done} chunks indsat")
    return done
