from __future__ import annotations

# One-time backfill: re-run the clean_body() pipeline over every emails.body_text
# in the database and overwrite emails.body_cleaned with the new result.
# body_text is read-only — only body_cleaned is mutated. The script is
# idempotent: rows whose new cleaned text is byte-identical to the existing
# body_cleaned are skipped, so a second run produces zero updates.
#
# Usage:
#   python run_clean_backfill.py [--voyage KEY] [--limit N]
#                                [--batch-size 500] [--dry-run]

# Allow running as `python run_clean_backfill.py` from src/01_preprocessing/
# in addition to `python -m src.preprocessing.run_clean_backfill`.
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

import psycopg
from tqdm import tqdm

from core.db import connect
from step_01_ingest.clean.clean_body import clean_body


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Re-clean emails.body_cleaned in place.")
    p.add_argument("--voyage", type=str, default=None, help="Only backfill this VOYAGE_KEY.")
    p.add_argument("--limit", type=int, default=None, help="Process at most N rows.")
    p.add_argument("--batch-size", type=int, default=500, help="Rows per UPDATE batch.")
    p.add_argument("--dry-run", action="store_true", help="No DB writes; print would-change stats.")
    return p.parse_args()


def _flush(conn: psycopg.Connection, batch: list[tuple[str | None, str]]) -> None:
    if not batch:
        return
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE emails SET body_cleaned = %s WHERE email_id = %s",
            batch,
        )
    conn.commit()


def main() -> int:
    args = _parse_args()

    where = ""
    where_args: list = []
    if args.voyage:
        where = " WHERE voyage_key = %s"
        where_args.append(args.voyage)

    select_sql = (
        f"SELECT email_id, body_text, body_cleaned FROM emails{where}"
        f" ORDER BY email_id"
        + (" LIMIT %s" if args.limit else "")
    )
    select_args = list(where_args) + ([args.limit] if args.limit else [])

    t0 = time.time()
    n_scanned = 0
    n_updated = 0
    n_unchanged = 0
    n_to_null = 0
    delta_chars = 0
    batch: list[tuple[str | None, str]] = []

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM emails{where}", where_args)
            total = cur.fetchone()[0]
        if args.limit:
            total = min(total, args.limit)

        with conn.cursor() as cur:
            cur.execute(select_sql, select_args)
            rows = cur.fetchall()

        for email_id, body_text, body_cleaned_old in tqdm(rows, total=total, desc="backfill", unit="email"):
            n_scanned += 1
            new_cleaned = clean_body(body_text)
            if new_cleaned == body_cleaned_old:
                n_unchanged += 1
                continue
            if new_cleaned is None:
                n_to_null += 1
            old_len = len(body_cleaned_old or "")
            new_len = len(new_cleaned or "")
            delta_chars += new_len - old_len
            n_updated += 1
            if not args.dry_run:
                batch.append((new_cleaned, str(email_id)))
                if len(batch) >= args.batch_size:
                    _flush(conn, batch)
                    batch.clear()
        if not args.dry_run:
            _flush(conn, batch)

    wall = time.time() - t0
    avg_delta = (delta_chars / n_updated) if n_updated else 0.0
    rate = (n_scanned / wall) if wall > 0 else 0.0

    print()
    print(f"  scanned        : {n_scanned}")
    print(f"  unchanged      : {n_unchanged}")
    print(f"  updated        : {n_updated}{'  (dry-run, no DB writes)' if args.dry_run else ''}")
    print(f"  cleaned -> NULL: {n_to_null}")
    print(f"  avg length delta: {avg_delta:+.1f} chars/row")
    print(f"  wall time      : {wall:.1f}s ({rate:.0f} rows/s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
