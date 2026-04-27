from __future__ import annotations

# Step 2 of the summaries pipeline. Map-reduces email summaries into a voyage narrative:
# MAP — generates phase summaries for batches of 50 emails in parallel;
# REDUCE — combines all phase summaries into a single voyage story via LLM.
# Writes to phase_summaries and voyage_summaries tables.
# Called from run_summaries.py; depends on llm_client, prompts, and shared/logging.

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from uuid import UUID

import psycopg

from shared.logging.run_logger import step
from step_08_summaries.llm_client import LLMClient
from step_08_summaries.prompts import (
    FIXTURE_SUMMARY_SYSTEM,
    PHASE_SUMMARY_SYSTEM,
    VOYAGE_SUMMARY_SYSTEM,
    build_fixture_summary_prompt,
    build_phase_summary_prompt,
    build_voyage_summary_from_phases_prompt,
)

PHASE_BATCH_SIZE = 50
PHASE_MAX_TOKENS = 2048
VOYAGE_MAX_TOKENS = 16384
DEFAULT_WORKERS = 4


def _format_ts(ts) -> str:
    if isinstance(ts, datetime):
        if ts.hour == 0 and ts.minute == 0 and ts.second == 0:
            return ts.strftime("%Y-%m-%d")
        return ts.strftime("%Y-%m-%d %H:%M %Z").strip()
    return str(ts)[:16] if ts else "unknown"


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


def get_email_summaries(conn: psycopg.Connection, voyage_key: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT s.sent_at, s.summary, e.direction
            FROM email_attach_summaries s
            LEFT JOIN emails e ON e.email_id = s.email_id
            WHERE s.voyage_key = %s AND s.status = 'ok'
            ORDER BY s.sent_at ASC NULLS LAST
        """, (voyage_key,))
        return [
            {"date": _format_ts(r[0]), "sent_at": r[0], "status": (r[2] or "UNKNOWN").upper(), "summary": r[1] or ""}
            for r in cur.fetchall()
        ]


def get_fixture(conn: psycopg.Connection, voyage_key: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM fixtures WHERE voyage_key = %s", (voyage_key,))
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d.name for d in cur.description]
        return dict(zip(cols, row))


def _generate_fixture_summary(fixture: dict, llm: LLMClient) -> str:
    summary, _ = llm.chat_with_usage(
        FIXTURE_SUMMARY_SYSTEM,
        build_fixture_summary_prompt(fixture),
        max_tokens=512,
    )
    return summary


def get_existing_phases(conn: psycopg.Connection, voyage_key: str) -> dict[int, dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT phase_index, phase_range, date_start, date_end, email_count, summary, status
            FROM phase_summaries WHERE voyage_key = %s
        """, (voyage_key,))
        return {
            r[0]: {
                "phase_index": r[0], "phase_range": r[1],
                "date_start": _format_ts(r[2]) if r[2] else "",
                "date_end": _format_ts(r[3]) if r[3] else "",
                "email_count": r[4], "summary": r[5] or "", "status": r[6],
            }
            for r in cur.fetchall()
        }


def _run_phase(voyage_key: str, phase_index: int, batch: list[dict], llm: LLMClient) -> dict:
    first = phase_index * PHASE_BATCH_SIZE + 1
    phase_range = f"emails {first}-{first + len(batch) - 1}"
    base = {
        "voyage_key": voyage_key, "phase_index": phase_index, "phase_range": phase_range,
        "date_start": batch[0].get("sent_at"), "date_end": batch[-1].get("sent_at"),
        "email_count": len(batch),
    }
    t0 = time.monotonic()
    try:
        summary, _ = llm.chat_with_usage(
            PHASE_SUMMARY_SYSTEM,
            build_phase_summary_prompt(voyage_key, phase_range, batch),
            max_tokens=PHASE_MAX_TOKENS,
        )
        return {**base, "status": "ok", "summary": summary, "secs": time.monotonic() - t0}
    except Exception as exc:
        return {**base, "status": "error", "error": f"{type(exc).__name__}: {exc}"}


def _upsert_phase(conn: psycopg.Connection, r: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM phase_summaries WHERE voyage_key = %s AND phase_index = %s",
            (r["voyage_key"], r["phase_index"]),
        )
        if r["status"] == "ok":
            cur.execute(
                """
                INSERT INTO phase_summaries
                    (voyage_key, phase_index, phase_range, date_start, date_end,
                     email_count, summary, status, log, generated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'ok', %s, %s)
                """,
                (r["voyage_key"], r["phase_index"], r["phase_range"],
                 r["date_start"], r["date_end"], r["email_count"], r["summary"],
                 f"OK {r['secs']:.1f}s", datetime.now(timezone.utc)),
            )
        else:
            cur.execute(
                """
                INSERT INTO phase_summaries
                    (voyage_key, phase_index, phase_range, date_start, date_end,
                     email_count, summary, status, log, generated_at)
                VALUES (%s, %s, %s, %s, %s, %s, '', 'error', %s, %s)
                """,
                (r["voyage_key"], r["phase_index"], r["phase_range"],
                 r["date_start"], r["date_end"], r["email_count"],
                 r["error"], datetime.now(timezone.utc)),
            )
    conn.commit()


def run(
    conn: psycopg.Connection,
    run_id: UUID,
    limit: int | None = None,
    llm: LLMClient | None = None,
    logger: logging.Logger | None = None,
    workers: int = DEFAULT_WORKERS,
) -> int:
    log = logger or logging.getLogger("summaries")

    if llm is None:
        llm = LLMClient()
        log.info(f"[step2] Model: {llm.model} @ {llm.base_url}")

    with step(conn, run_id, "voyage_summaries") as timer:
        pending = get_pending_voyages(conn, limit=limit)
        timer.rows_in = len(pending)

        if not pending:
            log.info("[step2] Ingen voyages at behandle — alt er up to date.")
            return 0

        log.info(f"[step2] {len(pending)} voyage(s) | {workers} workers | batch={PHASE_BATCH_SIZE}")
        generated = 0

        for i, voyage_key in enumerate(pending, 1):
            emails = get_email_summaries(conn, voyage_key)
            if not emails:
                log.warning(f"  [step2 {i}/{len(pending)}] {voyage_key} → ingen email summaries, springer over")
                continue

            fixture = get_fixture(conn, voyage_key)
            fixture_paragraph: str | None = None
            if fixture:
                try:
                    fixture_paragraph = _generate_fixture_summary(fixture, llm)
                    log.info(f"  [step2 {i}/{len(pending)}] {voyage_key} fixture summary OK")
                except Exception as exc:
                    log.warning(f"  [step2 {i}/{len(pending)}] {voyage_key} fixture summary FEJL: {exc}")

            batches = [emails[j:j + PHASE_BATCH_SIZE] for j in range(0, len(emails), PHASE_BATCH_SIZE)]
            existing = get_existing_phases(conn, voyage_key)
            missing = [(idx, b) for idx, b in enumerate(batches) if existing.get(idx, {}).get("status") != "ok"]

            log.info(f"  [step2 {i}/{len(pending)}] {voyage_key} | {len(emails)} emails → {len(batches)} faser ({len(missing)} missing)")

            # MAP: kør manglende faser parallelt
            if missing:
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    for future in as_completed({ex.submit(_run_phase, voyage_key, idx, b, llm): idx for idx, b in missing}):
                        r = future.result()
                        _upsert_phase(conn, r)
                        if r["status"] == "ok":
                            log.info(f"    [map] {voyage_key} fase {r['phase_index']+1}/{len(batches)} OK ({r['secs']:.1f}s)")
                        else:
                            log.error(f"    [map] {voyage_key} fase {r['phase_index']+1}/{len(batches)} FEJL: {r['error']}")

            # Verificer at alle faser er OK før reduce
            ok_phases = sorted(
                [p for p in get_existing_phases(conn, voyage_key).values() if p["status"] == "ok"],
                key=lambda p: p["phase_index"],
            )
            if len(ok_phases) != len(batches):
                log.warning(f"  [step2 {i}/{len(pending)}] {voyage_key} → {len(batches) - len(ok_phases)} fase(r) fejlede, springer over")
                timer.errors += 1
                continue

            # REDUCE: kombiner faser til voyage summary
            t0 = time.monotonic()
            try:
                voyage_summary, _ = llm.chat_with_usage(
                    VOYAGE_SUMMARY_SYSTEM,
                    build_voyage_summary_from_phases_prompt(voyage_key, fixture_paragraph, ok_phases),
                    max_tokens=VOYAGE_MAX_TOKENS,
                )
            except Exception as exc:
                log.error(f"  [step2 {i}/{len(pending)}] {voyage_key} → reduce FEJL: {exc}")
                timer.errors += 1
                continue

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO voyage_summaries (voyage_key, summary, email_count, has_fixture, generated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (voyage_key) DO UPDATE SET
                        summary = EXCLUDED.summary, email_count = EXCLUDED.email_count,
                        has_fixture = EXCLUDED.has_fixture, generated_at = EXCLUDED.generated_at
                    """,
                    (voyage_key, voyage_summary, len(emails), fixture_paragraph is not None, datetime.now(timezone.utc)),
                )
            conn.commit()
            generated += 1
            log.info(f"  [step2 {i}/{len(pending)}] {voyage_key} OK ({time.monotonic() - t0:.1f}s)")

        timer.rows_out = generated

    log.info(f"[step2] Færdig: {generated}/{len(pending)} voyage summaries genereret.")
    return generated
