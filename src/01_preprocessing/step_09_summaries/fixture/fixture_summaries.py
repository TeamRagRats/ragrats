from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from uuid import UUID

import psycopg

from shared.logging.run_logger import step
from ..llm_client import LLMClient
from .prompts import FIXTURE_SUMMARY_SYSTEM, build_fixture_summary_prompt


def get_pending_fixtures(conn: psycopg.Connection, limit: int | None = None) -> list[str]:
    sql = """
        SELECT voyage_key FROM fixtures
        WHERE voyage_key NOT IN (
            SELECT voyage_key FROM fixture_summaries WHERE status = 'ok'
        )
        ORDER BY voyage_key
    """
    if limit:
        sql += f" LIMIT {limit}"
    with conn.cursor() as cur:
        cur.execute(sql)
        return [r[0] for r in cur.fetchall()]


def get_fixture(conn: psycopg.Connection, voyage_key: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM fixtures WHERE voyage_key = %s", (voyage_key,))
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d.name for d in cur.description]
        return dict(zip(cols, row))


def run(
    conn: psycopg.Connection,
    run_id: UUID,
    limit: int | None = None,
    llm: LLMClient | None = None,
    logger: logging.Logger | None = None,
    voyage_key: str | None = None,
) -> int:
    log = logger or logging.getLogger("fixture_summaries")

    if llm is None:
        llm = LLMClient()
        log.info(f"[fixture] Model: {llm.model} @ {llm.base_url}")

    with step(conn, run_id, "fixture_summaries") as timer:
        if voyage_key:
            pending = [voyage_key]
        else:
            pending = get_pending_fixtures(conn, limit=limit)
        timer.rows_in = len(pending)

        if not pending:
            log.info("[fixture] Ingen fixtures at behandle — alt er up to date.")
            return 0

        log.info(f"[fixture] {len(pending)} fixture(s) at behandle")
        generated = 0

        for i, vk in enumerate(pending, 1):
            fixture = get_fixture(conn, vk)
            if fixture is None:
                log.warning(f"  [fixture {i}/{len(pending)}] {vk} → ingen fixture fundet, springer over")
                continue

            user_prompt = build_fixture_summary_prompt(fixture)
            t0 = time.monotonic()
            try:
                summary, _ = llm.chat_with_usage(
                    FIXTURE_SUMMARY_SYSTEM,
                    user_prompt,
                    max_tokens=512,
                )
                secs = time.monotonic() - t0
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO fixture_summaries (voyage_key, summary, status, log, generated_at, llm_input)
                        VALUES (%s, %s, 'ok', %s, %s, %s)
                        ON CONFLICT (voyage_key) DO UPDATE SET
                            summary = EXCLUDED.summary, status = 'ok',
                            log = EXCLUDED.log, generated_at = EXCLUDED.generated_at,
                            llm_input = EXCLUDED.llm_input
                        """,
                        (vk, summary, f"OK {secs:.1f}s", datetime.now(timezone.utc), user_prompt),
                    )
                conn.commit()
                generated += 1
                log.info(f"  [fixture {i}/{len(pending)}] {vk} OK ({secs:.1f}s)")
            except Exception as exc:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO fixture_summaries (voyage_key, summary, status, log, generated_at, llm_input)
                        VALUES (%s, '', 'error', %s, %s, %s)
                        ON CONFLICT (voyage_key) DO UPDATE SET
                            status = 'error', log = EXCLUDED.log,
                            generated_at = EXCLUDED.generated_at,
                            llm_input = EXCLUDED.llm_input
                        """,
                        (vk, f"{type(exc).__name__}: {exc}", datetime.now(timezone.utc), user_prompt),
                    )
                conn.commit()
                timer.errors += 1
                log.error(f"  [fixture {i}/{len(pending)}] {vk} → FEJL: {exc}")

        timer.rows_out = generated

    log.info(f"[fixture] Færdig: {generated}/{len(pending)} fixture summaries genereret.")
    return generated
