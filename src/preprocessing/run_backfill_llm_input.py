from __future__ import annotations

# Backfill llm_input column on all five summary tables for existing rows.
# Reconstructs each prompt from source data using the same build_*_prompt functions
# used by the live pipelines. No LLM calls are made.
# Run: python -m src.preprocessing.run_backfill_llm_input [--table NAME] [--dry-run]

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _repo_root = _here.parents[1]
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_here))
    __package__ = "src.preprocessing"

import argparse
import logging
import sys
from datetime import datetime

import psycopg

from shared.db import connect

from step_09_summaries.email_attach.email_summaries import get_attachments
from step_09_summaries.email_attach.prompts import build_email_summary_prompt
from step_09_summaries.fixture.fixture_summaries import get_fixture
from step_09_summaries.fixture.prompts import build_fixture_summary_prompt
from step_09_summaries.phase.phase_summaries import (
    compute_batch_size,
    get_email_summaries,
)
from step_09_summaries.phase.prompts import build_phase_summary_prompt
from step_09_summaries.voyage.voyage_summaries import get_fixture_summary, get_ok_phases
from step_09_summaries.voyage.prompts import build_voyage_summary_from_phases_prompt
from step_09_summaries.threads.thread_summaries import get_thread_emails
from step_09_summaries.threads.prompts import build_thread_summary_prompt

ALL_TABLES = ["email_attach", "fixture", "phase", "voyage", "thread"]

log = logging.getLogger("backfill_llm_input")


def _format_ts(ts) -> str:
    if isinstance(ts, datetime):
        if ts.hour == 0 and ts.minute == 0 and ts.second == 0:
            return ts.strftime("%Y-%m-%d")
        return ts.strftime("%Y-%m-%d %H:%M %Z").strip()
    return str(ts)[:16] if ts else "unknown date"


def backfill_email_attach(conn: psycopg.Connection, dry_run: bool) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT s.email_id, e.direction, e.sent_at, e.body_cleaned
            FROM email_attach_summaries s
            JOIN emails e ON e.email_id = s.email_id
            WHERE s.llm_input IS NULL
            ORDER BY s.email_id
        """)
        rows = cur.fetchall()

    log.info(f"  [email_attach] {len(rows)} rows to backfill")
    if dry_run or not rows:
        return len(rows)

    updated = 0
    with conn.cursor() as cur:
        for email_id, direction, sent_at, body in rows:
            attachments = get_attachments(conn, str(email_id))
            prompt = build_email_summary_prompt(
                direction=(direction or "UNKNOWN").upper(),
                date=_format_ts(sent_at),
                body=body or "",
                attachments=attachments,
            )
            cur.execute(
                "UPDATE email_attach_summaries SET llm_input = %s WHERE email_id = %s",
                (prompt, email_id),
            )
            updated += 1
    conn.commit()
    return updated


def backfill_fixture(conn: psycopg.Connection, dry_run: bool) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT voyage_key FROM fixture_summaries WHERE llm_input IS NULL ORDER BY voyage_key
        """)
        rows = cur.fetchall()

    log.info(f"  [fixture] {len(rows)} rows to backfill")
    if dry_run or not rows:
        return len(rows)

    updated = 0
    with conn.cursor() as cur:
        for (voyage_key,) in rows:
            fixture = get_fixture(conn, voyage_key)
            if fixture is None:
                log.warning(f"    [fixture] {voyage_key} → no fixture data, skipping")
                continue
            prompt = build_fixture_summary_prompt(fixture)
            cur.execute(
                "UPDATE fixture_summaries SET llm_input = %s WHERE voyage_key = %s",
                (prompt, voyage_key),
            )
            updated += 1
    conn.commit()
    return updated


def backfill_phase(conn: psycopg.Connection, dry_run: bool) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT voyage_key, phase_index, phase_range
            FROM phase_summaries
            WHERE llm_input IS NULL
            ORDER BY voyage_key, phase_index
        """)
        rows = cur.fetchall()

    log.info(f"  [phase] {len(rows)} rows to backfill")
    if dry_run or not rows:
        return len(rows)

    voyage_cache: dict[str, list[dict]] = {}
    updated = 0
    with conn.cursor() as cur:
        for voyage_key, phase_index, phase_range in rows:
            if voyage_key not in voyage_cache:
                voyage_cache[voyage_key] = get_email_summaries(conn, voyage_key)
            emails = voyage_cache[voyage_key]
            if not emails:
                log.warning(f"    [phase] {voyage_key} phase {phase_index} → no email summaries, skipping")
                continue
            batch_size = compute_batch_size(len(emails))
            start = phase_index * batch_size
            batch = emails[start:start + batch_size]
            if not batch:
                log.warning(f"    [phase] {voyage_key} phase {phase_index} → batch out of range, skipping")
                continue
            prompt = build_phase_summary_prompt(voyage_key, phase_range, batch)
            cur.execute(
                "UPDATE phase_summaries SET llm_input = %s WHERE voyage_key = %s AND phase_index = %s",
                (prompt, voyage_key, phase_index),
            )
            updated += 1
    conn.commit()
    return updated


def backfill_voyage(conn: psycopg.Connection, dry_run: bool) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT voyage_key FROM voyage_summaries WHERE llm_input IS NULL ORDER BY voyage_key
        """)
        rows = cur.fetchall()

    log.info(f"  [voyage] {len(rows)} rows to backfill")
    if dry_run or not rows:
        return len(rows)

    updated = 0
    with conn.cursor() as cur:
        for (voyage_key,) in rows:
            ok_phases = get_ok_phases(conn, voyage_key)
            fixture_paragraph = get_fixture_summary(conn, voyage_key)
            prompt = build_voyage_summary_from_phases_prompt(voyage_key, fixture_paragraph, ok_phases)
            cur.execute(
                "UPDATE voyage_summaries SET llm_input = %s WHERE voyage_key = %s",
                (prompt, voyage_key),
            )
            updated += 1
    conn.commit()
    return updated


def backfill_thread(conn: psycopg.Connection, dry_run: bool) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT thread_id, voyage_key FROM thread_summaries WHERE llm_input IS NULL ORDER BY thread_id
        """)
        rows = cur.fetchall()

    log.info(f"  [thread] {len(rows)} rows to backfill")
    if dry_run or not rows:
        return len(rows)

    updated = 0
    with conn.cursor() as cur:
        for thread_id, voyage_key in rows:
            emails = get_thread_emails(conn, thread_id)
            if not emails:
                log.warning(f"    [thread] {thread_id} → no emails, skipping")
                continue
            subject = next((e["subject"] for e in emails if e.get("subject")), None)
            prompt = build_thread_summary_prompt(str(thread_id), voyage_key, subject, emails)
            cur.execute(
                "UPDATE thread_summaries SET llm_input = %s WHERE thread_id = %s",
                (prompt, thread_id),
            )
            updated += 1
    conn.commit()
    return updated


BACKFILLERS = {
    "email_attach": backfill_email_attach,
    "fixture": backfill_fixture,
    "phase": backfill_phase,
    "voyage": backfill_voyage,
    "thread": backfill_thread,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill llm_input column on summary tables")
    parser.add_argument(
        "--table", choices=ALL_TABLES, default=None,
        help="Backfill only this table (default: all)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print counts without writing anything",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    tables = [args.table] if args.table else ALL_TABLES
    dry = args.dry_run
    if dry:
        log.info("DRY RUN — no changes will be written")

    with connect() as conn:
        total = 0
        for table in tables:
            log.info(f"Backfilling: {table}")
            n = BACKFILLERS[table](conn, dry)
            log.info(f"  → {n} {'rows would be updated' if dry else 'rows updated'}")
            total += n

    log.info(f"Done. Total: {total} {'rows to update' if dry else 'rows updated'}.")


if __name__ == "__main__":
    main()
