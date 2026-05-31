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
from .prompts import EMAIL_THREAD_SUMMARY_SYSTEM, build_email_thread_summary_prompt

EMAIL_THREAD_MAX_TOKENS = 1024
NO_PRIOR_TEXT = "No prior emails."


def _format_ts(ts) -> str:
    if isinstance(ts, datetime):
        if ts.hour == 0 and ts.minute == 0 and ts.second == 0:
            return ts.strftime("%Y-%m-%d")
        return ts.strftime("%Y-%m-%d %H:%M %Z").strip()
    return str(ts)[:16] if ts else "unknown"


def get_pending_emails(
    conn: psycopg.Connection,
    limit: int | None = None,
    voyage_key: str | None = None,
    thread_id: str | None = None,
    email_id: str | None = None,
) -> list[dict]:
    where = ["e.email_id NOT IN (SELECT email_id FROM email_thread_summaries)"]
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
        SELECT e.email_id, e.thread_id, e.voyage_key, e.sent_at, e.subject
        FROM emails e
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
                "sent_at": r[3],
                "subject": r[4],
            }
            for r in cur.fetchall()
        ]


def get_prior_emails(
    conn: psycopg.Connection,
    thread_id: UUID,
    sent_at,
    email_id: UUID,
) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.email_id, e.from_addr, e.to_addr, e.sent_at, e.body_cleaned
            FROM emails e
            WHERE e.thread_id = %s
            ORDER BY e.sent_at ASC NULLS LAST, e.email_id ASC
            """,
            (thread_id,),
        )
        rows = cur.fetchall()

    target_key = (sent_at is None, sent_at, str(email_id))
    prior = []
    for r in rows:
        eid, from_addr, to_addr, ts, body = r
        key = (ts is None, ts, str(eid))
        if key < target_key:
            prior.append({
                "from_addr": from_addr,
                "to_addr": to_addr or [],
                "date": _format_ts(ts),
                "sent_at": ts,
                "body_cleaned": body or "",
            })
    return prior


def _run_email_thread(
    email_id: UUID,
    thread_id: UUID,
    voyage_key: str,
    subject: str | None,
    prior_emails: list[dict],
    llm: LLMClient,
) -> dict:
    base = {
        "email_id": email_id,
        "thread_id": thread_id,
        "voyage_key": voyage_key,
        "subject": subject,
        "prior_count": len(prior_emails),
    }
    user_prompt = build_email_thread_summary_prompt(
        str(email_id), str(thread_id), voyage_key, subject, prior_emails
    )
    t0 = time.monotonic()
    try:
        summary, usage = llm.chat_with_usage(
            EMAIL_THREAD_SUMMARY_SYSTEM,
            user_prompt,
            max_tokens=EMAIL_THREAD_MAX_TOKENS,
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


def _upsert_email_thread(conn: psycopg.Connection, r: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM email_thread_summaries WHERE email_id = %s",
            (r["email_id"],),
        )
        if r["status"] == "ok":
            cur.execute(
                """
                INSERT INTO email_thread_summaries
                    (email_id, thread_id, voyage_key, prior_count, summary, status, log, generated_at, llm_input)
                VALUES (%s, %s, %s, %s, %s, 'ok', %s, %s, %s)
                """,
                (r["email_id"], r["thread_id"], r["voyage_key"], r["prior_count"],
                 r["summary"], r.get("log") or f"OK {r.get('secs', 0):.1f}s",
                 datetime.now(timezone.utc), r.get("llm_input")),
            )
        else:
            cur.execute(
                """
                INSERT INTO email_thread_summaries
                    (email_id, thread_id, voyage_key, prior_count, summary, status, log, generated_at, llm_input)
                VALUES (%s, %s, %s, %s, '', 'error', %s, %s, %s)
                """,
                (r["email_id"], r["thread_id"], r["voyage_key"], r["prior_count"],
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
    log = logger or logging.getLogger("email_thread_summaries")

    if llm is None:
        llm = LLMClient()
        log.info(f"[email_thread] Model: {llm.model} @ {llm.base_url}")

    with step(conn, run_id, "email_thread_summaries") as timer:
        pending = get_pending_emails(
            conn, limit=limit, voyage_key=voyage_key,
            thread_id=thread_id, email_id=email_id,
        )
        timer.rows_in = len(pending)

        if not pending:
            log.info("[email_thread] No emails to process — everything is up to date.")
            return 0

        log.info(f"[email_thread] {len(pending)} email(s) | {workers} workers")
        generated = 0

        started_at = datetime.now(timezone.utc)
        for item in pending:
            log_summary_pending(
                conn,
                summary_type="email_thread",
                entity_key=str(item["email_id"]),
                voyage_key=item["voyage_key"],
                started_at=started_at,
                run_id=run_id,
                batch_idx=0,
            )

        def _process(item: dict) -> dict:
            eid = item["email_id"]
            tid = item["thread_id"]
            vk = item["voyage_key"]
            subject = item.get("subject")
            prior = get_prior_emails(conn, tid, item["sent_at"], eid)

            if not prior:
                return {
                    "email_id": eid, "thread_id": tid, "voyage_key": vk,
                    "subject": subject, "prior_count": 0, "status": "ok",
                    "summary": NO_PRIOR_TEXT, "secs": 0.0,
                    "llm_input": None, "log": "OK no-prior",
                }

            return _run_email_thread(eid, tid, vk, subject, prior, llm)

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_process, item): item for item in pending}
            for i, future in enumerate(as_completed(futures), 1):
                r = future.result()
                _upsert_email_thread(conn, r)
                finished_at = datetime.now(timezone.utc)
                duration_ms = int(r.get("secs", 0) * 1000)
                if r["status"] == "ok":
                    log_summary_finished(
                        conn, summary_type="email_thread", entity_key=str(r["email_id"]),
                        finished_at=finished_at, duration_ms=duration_ms, status="ok",
                        input_tokens=r.get("input_tokens"), output_tokens=r.get("output_tokens"),
                    )
                    log.info(f"  [email_thread {i}/{len(pending)}] {r['email_id']} OK "
                             f"({r.get('secs', 0):.1f}s, {r['prior_count']} prior)")
                    generated += 1
                else:
                    log_summary_finished(
                        conn, summary_type="email_thread", entity_key=str(r["email_id"]),
                        finished_at=finished_at, duration_ms=duration_ms, status="error",
                        error_message=r.get("error"),
                    )
                    log.error(f"  [email_thread {i}/{len(pending)}] {r['email_id']} ERROR: {r['error']}")
                    timer.errors += 1

        timer.rows_out = generated

    log.info(f"[email_thread] Done: {generated} email(s) generated.")
    return generated
