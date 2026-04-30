from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from uuid import UUID

import psycopg

from shared.logging.run_logger import step
from ..llm_client import LLMClient
from .prompts import THREAD_SUMMARY_SYSTEM, build_thread_summary_prompt

THREAD_MAX_TOKENS = 1024


def _format_ts(ts) -> str:
    if isinstance(ts, datetime):
        if ts.hour == 0 and ts.minute == 0 and ts.second == 0:
            return ts.strftime("%Y-%m-%d")
        return ts.strftime("%Y-%m-%d %H:%M %Z").strip()
    return str(ts)[:16] if ts else "unknown"


def get_pending_threads(
    conn: psycopg.Connection,
    limit: int | None = None,
    voyage_key: str | None = None,
) -> list[dict]:
    if voyage_key:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT e.thread_id, e.voyage_key
                FROM emails e
                WHERE e.voyage_key = %s
                  AND e.thread_id NOT IN (SELECT thread_id FROM thread_summaries)
                ORDER BY e.thread_id
            """, (voyage_key,))
            rows = cur.fetchall()
    else:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT e.thread_id, e.voyage_key
                FROM emails e
                WHERE e.thread_id NOT IN (SELECT thread_id FROM thread_summaries)
                ORDER BY e.voyage_key, e.thread_id
            """)
            rows = cur.fetchall()

    result = [{"thread_id": r[0], "voyage_key": r[1]} for r in rows]
    return result[:limit] if limit else result


def get_thread_emails(conn: psycopg.Connection, thread_id: UUID) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT e.from_addr, e.to_addr, e.sent_at, e.subject,
                   s.summary
            FROM emails e
            LEFT JOIN email_attach_summaries s ON s.email_id = e.email_id AND s.status = 'ok'
            WHERE e.thread_id = %s
            ORDER BY e.sent_at ASC NULLS LAST
        """, (thread_id,))
        return [
            {
                "from_addr": r[0],
                "to_addr": r[1] or [],
                "date": _format_ts(r[2]),
                "sent_at": r[2],
                "subject": r[3],
                "summary": r[4] or "",
            }
            for r in cur.fetchall()
        ]


def _run_thread(thread_id: UUID, voyage_key: str, subject: str | None, emails: list[dict], llm: LLMClient) -> dict:
    base = {
        "thread_id": thread_id,
        "voyage_key": voyage_key,
        "subject": subject,
        "email_count": len(emails),
    }
    user_prompt = build_thread_summary_prompt(str(thread_id), voyage_key, subject, emails)
    t0 = time.monotonic()
    try:
        summary, _ = llm.chat_with_usage(
            THREAD_SUMMARY_SYSTEM,
            user_prompt,
            max_tokens=THREAD_MAX_TOKENS,
        )
        return {**base, "status": "ok", "summary": summary, "secs": time.monotonic() - t0, "llm_input": user_prompt}
    except Exception as exc:
        return {**base, "status": "error", "error": f"{type(exc).__name__}: {exc}", "llm_input": user_prompt}


def _upsert_thread(conn: psycopg.Connection, r: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM thread_summaries WHERE thread_id = %s",
            (r["thread_id"],),
        )
        if r["status"] == "ok":
            cur.execute(
                """
                INSERT INTO thread_summaries
                    (thread_id, voyage_key, subject, email_count, summary, status, log, generated_at, llm_input)
                VALUES (%s, %s, %s, %s, %s, 'ok', %s, %s, %s)
                """,
                (r["thread_id"], r["voyage_key"], r["subject"], r["email_count"],
                 r["summary"], f"OK {r['secs']:.1f}s", datetime.now(timezone.utc), r.get("llm_input")),
            )
        else:
            cur.execute(
                """
                INSERT INTO thread_summaries
                    (thread_id, voyage_key, subject, email_count, summary, status, log, generated_at, llm_input)
                VALUES (%s, %s, %s, %s, '', 'error', %s, %s, %s)
                """,
                (r["thread_id"], r["voyage_key"], r["subject"], r["email_count"],
                 r["error"], datetime.now(timezone.utc), r.get("llm_input")),
            )
    conn.commit()


def run(
    conn: psycopg.Connection,
    run_id: UUID,
    limit: int | None = None,
    llm: LLMClient | None = None,
    logger: logging.Logger | None = None,
    workers: int = 4,
    voyage_key: str | None = None,
    thread_id: str | None = None,
) -> int:
    log = logger or logging.getLogger("thread_summaries")

    if llm is None:
        llm = LLMClient()
        log.info(f"[thread] Model: {llm.model} @ {llm.base_url}")

    with step(conn, run_id, "thread_summaries") as timer:
        if thread_id:
            with conn.cursor() as cur:
                cur.execute("SELECT voyage_key FROM emails WHERE thread_id = %s LIMIT 1", (thread_id,))
                row = cur.fetchone()
            if not row:
                log.error(f"[thread] thread_id {thread_id} ikke fundet i emails-tabellen")
                return 0
            pending = [{"thread_id": thread_id, "voyage_key": row[0]}]
        else:
            pending = get_pending_threads(conn, limit=limit, voyage_key=voyage_key)
        timer.rows_in = len(pending)

        if not pending:
            log.info("[thread] Ingen tråde at behandle — alt er up to date.")
            return 0

        log.info(f"[thread] {len(pending)} tråd(e) | {workers} workers")
        generated = 0

        def _process(item: dict) -> dict:
            tid = item["thread_id"]
            vk = item["voyage_key"]
            emails = get_thread_emails(conn, tid)
            if not emails:
                log.warning(f"  [thread] {tid} → ingen emails, springer over")
                return {"thread_id": tid, "voyage_key": vk, "skipped": True}

            has_summaries = any(e["summary"] for e in emails)
            if not has_summaries:
                log.warning(f"  [thread] {tid} → ingen email_attach_summaries, springer over")
                return {"thread_id": tid, "voyage_key": vk, "skipped": True}

            subject = next((e["subject"] for e in emails if e.get("subject")), None)

            if len(emails) == 1:
                log.info(f"  [thread] {tid} → 1 email, kopierer email_attach summary")
                return {
                    "thread_id": tid, "voyage_key": vk, "subject": subject,
                    "email_count": 1, "status": "ok",
                    "summary": emails[0]["summary"],
                    "secs": 0.0, "llm_input": None,
                }

            return _run_thread(tid, vk, subject, emails, llm)

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_process, item): item for item in pending}
            for i, future in enumerate(as_completed(futures), 1):
                r = future.result()
                if r.get("skipped"):
                    continue
                _upsert_thread(conn, r)
                if r["status"] == "ok":
                    log.info(f"  [thread {i}/{len(pending)}] {r['thread_id']} OK ({r['secs']:.1f}s, {r['email_count']} emails)")
                    generated += 1
                else:
                    log.error(f"  [thread {i}/{len(pending)}] {r['thread_id']} FEJL: {r['error']}")
                    timer.errors += 1

        timer.rows_out = generated

    log.info(f"[thread] Færdig: {generated} tråd(e) genereret.")
    return generated
