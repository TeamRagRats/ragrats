from __future__ import annotations

# Main entry point for the ingest pipeline (steps 1–6).
# Discovers voyage mailbox folders, parses .eml + sidecar JSON, cleans bodies, assigns thread IDs,
# extracts attachments to disk, and upserts everything into Postgres.
# Supports --dry-run, --resume, --voyage filter, and --summary-only.
# Run: python run_ingest.py [--dry-run] [--voyage KEY] [--resume]

# Allow running as `python3 run_ingest.py` from inside src/preprocessing/
# in addition to `python -m src.preprocessing.run_ingest` from the repo root.
if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _repo_root = _here.parents[1]
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_here))
    __package__ = "src.preprocessing"

import argparse
import time
from collections import defaultdict
from pathlib import Path
from uuid import UUID

import psycopg
from tqdm import tqdm

from shared.config import Config, load_config
from shared.db import connect
from step_01_discover.pair_eml_json import validate_pairs
from step_01_discover.walk_mailbox import MailboxItem, walk_mailbox
from step_02_parse.merge_metadata import EmailRecord, merge_metadata
from step_02_parse.parse_eml import parse_eml
from step_02_parse.parse_json import parse_json
from step_03_clean.clean_body import clean_body
from step_04_thread.assign_thread_ids import assign_thread_ids
from step_05_attachments.extract_attachments import extract_attachments
from step_01_discover.read_fixtures_xlsx import read_fixtures_xlsx
from step_06_load.upsert_attachments import upsert_attachments
from step_06_load.upsert_emails import upsert_email
from step_06_load.upsert_fixtures import upsert_fixtures
from shared.logging.run_logger import (
    finish_run,
    record_ingest_logging,
    start_run,
    step,
)
from shared.logging.summary import (
    VoyageSummary,
    format_final_table,
    format_per_voyage_line,
    load_latest_summaries,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Import voyage mailbox into Postgres.")
    p.add_argument("--steps", type=str, default=None, help="Comma-separated step numbers (1..7).")
    p.add_argument("--voyage", type=str, default=None, help="Only import this VOYAGE_KEY.")
    p.add_argument("--dry-run", action="store_true", help="No DB writes, no file writes.")
    p.add_argument("--resume", action="store_true", help="Skip email_ids already in DB.")
    p.add_argument("--summary-only", action="store_true", help="Print per-voyage table and exit.")
    return p.parse_args()


def _existing_email_ids(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT email_id FROM emails")
        return {str(r[0]) for r in cur.fetchall()}


def _group_by_voyage(items: list[MailboxItem]) -> dict[str, list[MailboxItem]]:
    out: dict[str, list[MailboxItem]] = defaultdict(list)
    for it in items:
        out[it.voyage_key].append(it)
    return out


def _import_voyage(
    conn: psycopg.Connection | None,
    run_id: UUID | None,
    voyage_key: str,
    items: list[MailboxItem],
    cfg: Config,
    dry_run: bool,
) -> VoyageSummary:
    t0 = time.time()
    records: list[EmailRecord] = []
    errors = 0
    for item in tqdm(items, desc=f"parse {voyage_key}", unit="eml", leave=False):
        try:
            parsed = parse_eml(item.eml_path)
            sidecar = parse_json(item.json_path)
            rec = merge_metadata(voyage_key, item.eml_path, item.direction, parsed, sidecar)
            rec.body_cleaned = clean_body(rec.body_text)
            records.append(rec)
        except Exception as exc:  # per-file error logged; we continue the voyage
            errors += 1
            print(f"[error] {voyage_key} {item.eml_path}: {exc}")

    thread_map = assign_thread_ids(voyage_key, records)
    n_threads = len(set(thread_map.values()))
    n_attachments = 0
    n_bytes = 0

    for rec in tqdm(records, desc=f"load  {voyage_key}", unit="eml", leave=False):
        written = extract_attachments(
            cfg.attachment_root, voyage_key, rec.email_id, rec.attachments, dry_run=dry_run
        )
        n_attachments += len(written)
        n_bytes += sum(a.size_bytes for a in written)
        if dry_run or conn is None:
            continue
        with conn.cursor() as cur:
            upsert_email(
                cur,
                rec,
                thread_map[rec.email_id],
                has_attachment=bool(written),
                repo_root=cfg.repo_root,
            )
            upsert_attachments(cur, rec.email_id, voyage_key, written, repo_root=cfg.repo_root)
        conn.commit()

    wall_ms = int((time.time() - t0) * 1000)
    summary = VoyageSummary(
        voyage_key=voyage_key,
        n_emails=len(records),
        n_threads=n_threads,
        n_attachments=n_attachments,
        n_bytes=n_bytes,
        n_errors=errors,
        wall_time_ms=wall_ms,
    )
    print(format_per_voyage_line(summary))
    if not dry_run and conn is not None and run_id is not None:
        record_ingest_logging(
            conn,
            run_id,
            voyage_key,
            summary.n_emails,
            summary.n_threads,
            summary.n_attachments,
            summary.n_bytes,
            summary.n_errors,
            summary.wall_time_ms,
        )
    return summary


def run_summary_only() -> int:
    with connect() as conn:
        summaries = load_latest_summaries(conn)
    if not summaries:
        print("no import_runs yet")
        return 0
    print(format_final_table(summaries))
    return 0


def run_import(args: argparse.Namespace) -> int:
    cfg = load_config()

    fixture_path = cfg.repo_root / "data" / "ARC_FIXTURES_20.xlsx"
    if not args.dry_run and fixture_path.exists():
        rows = read_fixtures_xlsx(fixture_path)
        with connect() as conn:
            with conn.cursor() as cur:
                n = upsert_fixtures(cur, rows)
            conn.commit()
        print(f"[fixtures] upserted {n} rows")

    items_all = list(walk_mailbox(cfg.data_root))
    paired, pair_errors = validate_pairs(items_all)
    for e in pair_errors:
        print(f"[orphan] {e.voyage_key} {e.eml_path} missing {e.missing}")
    if args.voyage:
        paired = [i for i in paired if i.voyage_key == args.voyage]

    if args.dry_run:
        print(f"[dry-run] {len(paired)} paired items; no DB or file writes")
        by_voyage = _group_by_voyage(paired)
        summaries = [
            _import_voyage(None, None, vk, items, cfg, dry_run=True)
            for vk, items in sorted(by_voyage.items())
        ]
        print(format_final_table(summaries))
        return 0

    with connect() as conn:
        run_id = start_run(conn)
        status = "ok"
        try:
            if args.resume:
                existing = _existing_email_ids(conn)
                before = len(paired)
                paired = [i for i in paired if i.eml_path.stem not in existing]
                print(f"[resume] skipping {before - len(paired)} already-imported emails")

            by_voyage = _group_by_voyage(paired)
            summaries: list[VoyageSummary] = []
            with step(conn, run_id, "import_all") as timer:
                timer.rows_in = len(paired)
                for vk, items in sorted(by_voyage.items()):
                    summaries.append(_import_voyage(conn, run_id, vk, items, cfg, dry_run=False))
                timer.rows_out = sum(s.n_emails for s in summaries)
                timer.errors = sum(s.n_errors for s in summaries)
        except Exception:
            status = "failed"
            finish_run(conn, run_id, status)
            raise
        finish_run(conn, run_id, status)

    print()
    print(format_final_table(summaries))
    return 0


def main() -> int:
    args = _parse_args()
    if args.summary_only:
        return run_summary_only()
    return run_import(args)


if __name__ == "__main__":
    raise SystemExit(main())
