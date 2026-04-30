from __future__ import annotations

import gc
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from uuid import UUID

import psycopg

from core.logging.run_logger import step
from core.logging.log_summaries import log_summary_pending, log_summary_finished
from clients.llm_client import LLMClient
from .prompts import EMAIL_SUMMARY_SYSTEM, build_email_summary_prompt

BATCH_SIZE = 20


def _cleanup_memory(log: logging.Logger) -> None:
    collected = gc.collect()
    log.debug(f"GC collected {collected} objects")
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            log.debug("VRAM cleared")
    except ImportError:
        pass
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
        log.debug("malloc_trim(0)")
    except Exception:
        pass


def _format_ts(ts) -> str:
    if isinstance(ts, datetime):
        if ts.hour == 0 and ts.minute == 0 and ts.second == 0:
            return ts.strftime("%Y-%m-%d")
        return ts.strftime("%Y-%m-%d %H:%M %Z").strip()
    return str(ts)[:16] if ts else "unknown date"


def get_pending_emails(conn: psycopg.Connection, limit: int | None = None) -> list[dict]:
    sql = """
        SELECT e.email_id, e.voyage_key, e.sent_at, e.direction, e.body_cleaned
        FROM emails e
        WHERE e.email_id NOT IN (
            SELECT email_id FROM email_attach_summaries WHERE status = 'ok'
        )
        ORDER BY e.sent_at ASC NULLS LAST
    """
    if limit:
        sql += f" LIMIT {limit}"
    with conn.cursor() as cur:
        cur.execute(sql)
        return [
            {
                "email_id": str(r[0]),
                "voyage_key": r[1],
                "sent_at": r[2],
                "direction": (r[3] or "UNKNOWN").upper(),
                "body": r[4] or "",
            }
            for r in cur.fetchall()
        ]


def get_attachments(conn: psycopg.Connection, email_id: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT a.file_path, ls.structured_md
            FROM attachments a
            JOIN llm_structured ls ON ls.sha256 = a.sha256
            WHERE a.email_id = %s
              AND ls.structured_md IS NOT NULL
              AND TRIM(ls.structured_md) <> ''
        """, (email_id,))
        return [{"filename": r[0] or "", "content": r[1] or ""} for r in cur.fetchall()]


def _process_email(email: dict, llm: LLMClient) -> dict:
    user_prompt = build_email_summary_prompt(
        direction=email["direction"],
        date=_format_ts(email["sent_at"]),
        body=email["body"],
        attachments=email.get("attachments", []),
    )
    t0 = time.monotonic()
    try:
        summary, usage = llm.chat_with_usage(EMAIL_SUMMARY_SYSTEM, user_prompt)
        return {
            "status": "ok",
            "email_id": email["email_id"], "voyage_key": email["voyage_key"],
            "sent_at": email["sent_at"], "summary": summary,
            "secs": time.monotonic() - t0,
            "attach_count": len(email.get("attachments", [])),
            "llm_input": user_prompt,
            "input_tokens": usage["prompt_tokens"],
            "output_tokens": usage["completion_tokens"],
        }
    except Exception as exc:
        return {
            "status": "error",
            "email_id": email["email_id"], "voyage_key": email["voyage_key"],
            "sent_at": email["sent_at"],
            "error": f"{type(exc).__name__}: {exc}",
            "llm_input": user_prompt,
            "input_tokens": None, "output_tokens": None,
        }


def run(
    conn: psycopg.Connection,
    run_id: UUID,
    limit: int | None = None,
    llm: LLMClient | None = None,
    logger: logging.Logger | None = None,
    workers: int = 5,
) -> int:
    log = logger or logging.getLogger("summaries")

    if llm is None:
        llm = LLMClient()
        log.info(f"[step1] Model: {llm.model} @ {llm.base_url}")

    with step(conn, run_id, "email_summaries") as timer:
        pending = get_pending_emails(conn, limit=limit)
        timer.rows_in = len(pending)

        if not pending:
            log.info("[step1] Ingen emails at behandle — alt er up to date.")
            return 0

        batches = [pending[i:i + BATCH_SIZE] for i in range(0, len(pending), BATCH_SIZE)]
        log.info(f"[step1] {len(pending)} email(s) | {workers} workers | {len(batches)} batches")

        generated = 0
        done = 0

        for batch_idx, batch in enumerate(batches, 1):
            for email in batch:
                email["attachments"] = get_attachments(conn, email["email_id"])

            batch_started = datetime.now(timezone.utc)
            for email in batch:
                log_summary_pending(
                    conn,
                    summary_type="email_attach",
                    entity_key=email["email_id"],
                    voyage_key=email["voyage_key"],
                    started_at=batch_started,
                    run_id=run_id,
                    batch_idx=batch_idx,
                )

            batch_results: list[dict] = []
            with ThreadPoolExecutor(max_workers=workers) as executor:
                for future in as_completed({executor.submit(_process_email, e, llm): e for e in batch}):
                    done += 1
                    r = future.result()
                    batch_results.append(r)
                    finished_at = datetime.now(timezone.utc)
                    duration_ms = int(r.get("secs", 0) * 1000)
                    log_summary_finished(
                        conn,
                        summary_type="email_attach",
                        entity_key=r["email_id"],
                        finished_at=finished_at,
                        duration_ms=duration_ms,
                        status=r["status"],
                        error_message=r.get("error"),
                        input_tokens=r.get("input_tokens"),
                        output_tokens=r.get("output_tokens"),
                    )
                    if r["status"] == "ok":
                        attach_info = f" (+{r['attach_count']} attach)" if r["attach_count"] else ""
                        log.info(f"  [step1 {done}/{len(pending)}] {r['email_id']}{attach_info} OK ({r['secs']:.1f}s)")
                    else:
                        log.error(f"  [step1 {done}/{len(pending)}] {r['email_id']} → FEJL: {r['error']}")

            ok_count = 0
            err_count = 0
            with conn.cursor() as cur:
                batch_ids = [r["email_id"] for r in batch_results]
                if batch_ids:
                    cur.execute(
                        "DELETE FROM email_attach_summaries WHERE status='error' AND email_id = ANY(%s)",
                        (batch_ids,),
                    )
                for r in batch_results:
                    if r["status"] == "ok":
                        cur.execute(
                            """
                            INSERT INTO email_attach_summaries
                                (email_id, voyage_key, sent_at, summary, status, log, generated_at, llm_input)
                            VALUES (%s, %s, %s, %s, 'ok', %s, %s, %s)
                            ON CONFLICT (email_id) DO UPDATE SET
                                summary = EXCLUDED.summary, status = 'ok',
                                log = EXCLUDED.log, generated_at = EXCLUDED.generated_at,
                                llm_input = EXCLUDED.llm_input
                            """,
                            (r["email_id"], r["voyage_key"], r["sent_at"], r["summary"],
                             f"OK {r['secs']:.1f}s attach={r['attach_count']}",
                             datetime.now(timezone.utc), r["llm_input"]),
                        )
                        ok_count += 1
                    else:
                        cur.execute(
                            """
                            INSERT INTO email_attach_summaries
                                (email_id, voyage_key, sent_at, summary, status, log, generated_at, llm_input)
                            VALUES (%s, %s, %s, '', 'error', %s, %s, %s)
                            ON CONFLICT (email_id) DO UPDATE SET
                                status = 'error', log = EXCLUDED.log,
                                generated_at = EXCLUDED.generated_at,
                                llm_input = EXCLUDED.llm_input
                            """,
                            (r["email_id"], r["voyage_key"], r["sent_at"],
                             r["error"], datetime.now(timezone.utc), r["llm_input"]),
                        )
                        err_count += 1
            conn.commit()
            generated += ok_count
            log.info(f"  [step1 batch {batch_idx}/{len(batches)}] {ok_count} OK + {err_count} ERROR")

            for email in batch:
                email["attachments"] = []
                email["body"] = ""
            for r in batch_results:
                r["summary"] = ""
            batch_results.clear()
            _cleanup_memory(log)

        timer.rows_out = generated
        timer.errors = done - generated

    log.info(f"[step1] Færdig: {generated}/{len(pending)} summaries genereret.")
    return generated
