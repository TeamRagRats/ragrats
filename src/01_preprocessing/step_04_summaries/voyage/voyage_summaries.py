from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone
from uuid import UUID

import psycopg

from log.log_run import step
from log.log_summaries import log_summary_pending, log_summary_finished
from clients.llm_client import LLMClient
from .prompts import (
    VOYAGE_SUMMARY_SYSTEM,
    build_voyage_summary_from_phases_prompt,
)
PHASE_BATCH_SIZE = 10  # must match phase/phase_summaries.py
VOYAGE_MAX_TOKENS = 16384
DEFAULT_WORKERS = 1


def get_pending_voyages(conn: psycopg.Connection, limit: int | None = None) -> list[str]:
    sql = """
        SELECT DISTINCT voyage_key
        FROM email_attach_summaries
        WHERE voyage_key IS NOT NULL
          AND status = 'ok'
          AND voyage_key NOT IN (SELECT voyage_key FROM voyage_summaries)
        ORDER BY voyage_key
    """
    if limit:
        sql += f" LIMIT {limit}"
    with conn.cursor() as cur:
        cur.execute(sql)
        return [r[0] for r in cur.fetchall()]


def get_fixture_summary(conn: psycopg.Connection, voyage_key: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT summary FROM fixture_summaries WHERE voyage_key = %s AND status = 'ok'",
            (voyage_key,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def get_email_count(conn: psycopg.Connection, voyage_key: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM email_attach_summaries WHERE voyage_key = %s AND status = 'ok'",
            (voyage_key,),
        )
        return cur.fetchone()[0]


def get_ok_phases(conn: psycopg.Connection, voyage_key: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT phase_index, phase_range, date_start, date_end, email_count, summary
            FROM phase_summaries WHERE voyage_key = %s AND status = 'ok'
            ORDER BY phase_index
        """, (voyage_key,))
        return [
            {
                "phase_index": r[0], "phase_range": r[1],
                "date_start": str(r[2]) if r[2] else "",
                "date_end": str(r[3]) if r[3] else "",
                "email_count": r[4], "summary": r[5] or "",
            }
            for r in cur.fetchall()
        ]


def run(
    conn: psycopg.Connection,
    run_id: UUID,
    limit: int | None = None,
    llm: LLMClient | None = None,
    logger: logging.Logger | None = None,
    workers: int = DEFAULT_WORKERS,
    voyage_key: str | None = None,
) -> int:
    log = logger or logging.getLogger("voyage_summaries")

    if llm is None:
        llm = LLMClient()
        log.info(f"[voyage] Model: {llm.model} @ {llm.base_url}")

    with step(conn, run_id, "voyage_summaries") as timer:
        if voyage_key:
            pending = [voyage_key]
        else:
            pending = get_pending_voyages(conn, limit=limit)
        timer.rows_in = len(pending)

        if not pending:
            log.info("[voyage] Ingen voyages at behandle — alt er up to date.")
            return 0

        log.info(f"[voyage] {len(pending)} voyage(s) at reducere")
        generated = 0

        for i, vk in enumerate(pending, 1):
            email_count = get_email_count(conn, vk)
            if not email_count:
                log.warning(f"  [voyage {i}/{len(pending)}] {vk} → ingen emails, springer over")
                continue

            expected = math.ceil(email_count / PHASE_BATCH_SIZE)
            ok_phases = get_ok_phases(conn, vk)

            if len(ok_phases) != expected:
                log.warning(
                    f"  [voyage {i}/{len(pending)}] {vk} → {len(ok_phases)}/{expected} faser klar, "
                    f"kør run_phase_summaries.py først"
                )
                timer.errors += 1
                continue

            fixture_paragraph = get_fixture_summary(conn, vk)

            user_prompt = build_voyage_summary_from_phases_prompt(vk, fixture_paragraph, ok_phases)
            started_at = datetime.now(timezone.utc)
            log_summary_pending(
                conn,
                summary_type="voyage",
                entity_key=vk,
                voyage_key=vk,
                started_at=started_at,
                run_id=run_id,
                batch_idx=0,
            )
            t0 = time.monotonic()
            try:
                voyage_summary, usage = llm.chat_with_usage(
                    VOYAGE_SUMMARY_SYSTEM,
                    user_prompt,
                    max_tokens=VOYAGE_MAX_TOKENS,
                    temperature=0.1,
                )
            except Exception as exc:
                log_summary_finished(
                    conn, summary_type="voyage", entity_key=vk,
                    finished_at=datetime.now(timezone.utc), duration_ms=int((time.monotonic() - t0) * 1000),
                    status="error", error_message=f"{type(exc).__name__}: {exc}",
                )
                log.error(f"  [voyage {i}/{len(pending)}] {vk} → reduce FEJL: {exc}")
                timer.errors += 1
                continue

            secs = time.monotonic() - t0
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO voyage_summaries
                        (voyage_key, summary, email_count, has_fixture, generated_at, llm_input)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (voyage_key) DO UPDATE SET
                        summary = EXCLUDED.summary, email_count = EXCLUDED.email_count,
                        has_fixture = EXCLUDED.has_fixture, generated_at = EXCLUDED.generated_at,
                        llm_input = EXCLUDED.llm_input
                    """,
                    (vk, voyage_summary, email_count, fixture_paragraph is not None,
                     datetime.now(timezone.utc), user_prompt),
                )
            conn.commit()
            log_summary_finished(
                conn, summary_type="voyage", entity_key=vk,
                finished_at=datetime.now(timezone.utc), duration_ms=int(secs * 1000), status="ok",
                input_tokens=usage["prompt_tokens"], output_tokens=usage["completion_tokens"],
            )
            generated += 1
            log.info(f"  [voyage {i}/{len(pending)}] {vk} OK ({secs:.1f}s)")

        timer.rows_out = generated

    log.info(f"[voyage] Færdig: {generated}/{len(pending)} voyage summaries genereret.")
    return generated
