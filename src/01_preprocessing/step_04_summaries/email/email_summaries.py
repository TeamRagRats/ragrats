from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from uuid import UUID

import psycopg

from log.log_run import step
from log.log_summaries import log_summary_pending, log_summary_finished
from clients.llm_client import LLMClient
from .prompts import EMAIL_SUMMARY_SYSTEM, build_email_summary_prompt

EMAIL_SUMMARY_MAX_TOKENS = 768


def get_pending_emails(
    conn: psycopg.Connection,
    limit: int | None = None,
    voyage_key: str | None = None,
    thread_id: str | None = None,
    email_id: str | None = None,
) -> list[dict]:
    where = ["e.email_id NOT IN (SELECT email_id FROM email_summaries)"]
    params: list = []
    if voyage_key:
        where.append("e.voyage_key = %s")
        params.append(voyage_key)
    if thread_id:
        where.append("e.thread_id = %s")
        params.append(thread_id)
    if email_id:
        where.append("e.email_id = %s")
        params.append(email_id)

    sql = f"""
        SELECT e.email_id, e.thread_id, e.voyage_key, e.subject, e.body_cleaned,
               e.from_addr, e.to_addr, ets.summary AS thread_summary
        FROM emails e
        LEFT JOIN email_thread_summaries ets
               ON ets.email_id = e.email_id AND ets.status = 'ok'
        WHERE {' AND '.join(where)}
        ORDER BY e.thread_id, e.sent_at ASC NULLS LAST, e.email_id
    """
    if limit:
        sql += " LIMIT %s"
        params.append(limit)

    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [
            {
                "email_id": r[0],
                "thread_id": r[1],
                "voyage_key": r[2],
                "subject": r[3],
                "body_cleaned": r[4],
                "from_addr": r[5],
                "to_addr": r[6] or [],
                "thread_summary": r[7],
            }
            for r in cur.fetchall()
        ]


def _run_email(
    email_id: UUID,
    thread_id: UUID,
    voyage_key: str,
    subject: str | None,
    body_cleaned: str | None,
    thread_summary: str | None,
    from_addr: str | None,
    to_addr: list[str] | None,
    llm: LLMClient,
) -> dict:
    base = {
        "email_id": email_id,
        "thread_id": thread_id,
        "voyage_key": voyage_key,
    }
    user_prompt = build_email_summary_prompt(
        subject, body_cleaned, thread_summary, from_addr, to_addr
    )
    t0 = time.monotonic()
    try:
        summary, usage = llm.chat_with_usage(
            EMAIL_SUMMARY_SYSTEM,
            user_prompt,
            max_tokens=EMAIL_SUMMARY_MAX_TOKENS,
        )
        return {
            **base, "status": "ok", "summary": summary, "secs": time.monotonic() - t0,
            "llm_input": user_prompt,
            "input_tokens": usage["prompt_tokens"], "output_tokens": usage["completion_tokens"],
        }
    except Exception as exc:
        return {
            **base, "status": "error", "error": f"{type(exc).__name__}: {exc}",
            "llm_input": user_prompt, "input_tokens": None, "output_tokens": None,
        }


def _upsert_email_summary(conn: psycopg.Connection, r: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM email_summaries WHERE email_id = %s",
            (r["email_id"],),
        )
        if r["status"] == "ok":
            cur.execute(
                """
                INSERT INTO email_summaries
                    (email_id, thread_id, voyage_key, summary, status, log, generated_at, llm_input)
                VALUES (%s, %s, %s, %s, 'ok', %s, %s, %s)
                """,
                (r["email_id"], r["thread_id"], r["voyage_key"],
                 r["summary"], r.get("log") or f"OK {r.get('secs', 0):.1f}s",
                 datetime.now(timezone.utc), r.get("llm_input")),
            )
        else:
            cur.execute(
                """
                INSERT INTO email_summaries
                    (email_id, thread_id, voyage_key, summary, status, log, generated_at, llm_input)
                VALUES (%s, %s, %s, '', 'error', %s, %s, %s)
                """,
                (r["email_id"], r["thread_id"], r["voyage_key"],
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
    email_id: str | None = None,
) -> int:
    log = logger or logging.getLogger("email_summaries")

    if llm is None:
        llm = LLMClient()
        log.info(f"[email] Model: {llm.model} @ {llm.base_url}")

    with step(conn, run_id, "email_summaries") as timer:
        pending = get_pending_emails(
            conn, limit=limit, voyage_key=voyage_key,
            thread_id=thread_id, email_id=email_id,
        )
        timer.rows_in = len(pending)

        if not pending:
            log.info("[email] Ingen emails at behandle — alt er up to date.")
            return 0

        log.info(f"[email] {len(pending)} email(s) | {workers} workers")
        generated = 0

        started_at = datetime.now(timezone.utc)
        for item in pending:
            log_summary_pending(
                conn,
                summary_type="email",
                entity_key=str(item["email_id"]),
                voyage_key=item["voyage_key"],
                started_at=started_at,
                run_id=run_id,
                batch_idx=0,
            )

        def _process(item: dict) -> dict:
            return _run_email(
                item["email_id"], item["thread_id"], item["voyage_key"],
                item.get("subject"), item.get("body_cleaned"),
                item.get("thread_summary"),
                item.get("from_addr"), item.get("to_addr"),
                llm,
            )

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_process, item): item for item in pending}
            for i, future in enumerate(as_completed(futures), 1):
                r = future.result()
                _upsert_email_summary(conn, r)
                finished_at = datetime.now(timezone.utc)
                duration_ms = int(r.get("secs", 0) * 1000)
                if r["status"] == "ok":
                    log_summary_finished(
                        conn, summary_type="email", entity_key=str(r["email_id"]),
                        finished_at=finished_at, duration_ms=duration_ms, status="ok",
                        input_tokens=r.get("input_tokens"), output_tokens=r.get("output_tokens"),
                    )
                    log.info(f"  [email {i}/{len(pending)}] {r['email_id']} OK "
                             f"({r.get('secs', 0):.1f}s)")
                    generated += 1
                else:
                    log_summary_finished(
                        conn, summary_type="email", entity_key=str(r["email_id"]),
                        finished_at=finished_at, duration_ms=duration_ms, status="error",
                        error_message=r.get("error"),
                    )
                    log.error(f"  [email {i}/{len(pending)}] {r['email_id']} FEJL: {r['error']}")
                    timer.errors += 1

        timer.rows_out = generated

    log.info(f"[email] Færdig: {generated} email(s) genereret.")
    return generated
