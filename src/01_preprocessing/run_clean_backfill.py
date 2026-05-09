from __future__ import annotations

# Re-runs clean_body on rows in the emails table and updates body_cleaned.
# Use --only-null to limit the backfill to rows where body_cleaned IS NULL
# but body IS NOT NULL (the typical recovery case after fixing a clean_body
# bug). Default is all rows with non-null body — safe because clean_body is
# deterministic and re-runs of unchanged inputs produce unchanged output.
#
# Run: python -m src.01_preprocessing.run_clean_backfill [--only-null] [--dry-run] [--limit N]

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _repo_root = _here.parents[1]
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_here))
    __package__ = "src.01_preprocessing"

import argparse
import time

from tqdm import tqdm

from core.db import connect
from step_01_ingest.clean.clean_body import clean_body

COMMIT_EVERY = 500


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Re-run clean_body and update emails.body_cleaned.")
    p.add_argument("--only-null", action="store_true",
                   help="Only process rows where body_cleaned IS NULL/empty.")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute new values but do not write to DB.")
    p.add_argument("--limit", type=int, default=None,
                   help="Process at most N rows (for testing).")
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    where = "body IS NOT NULL AND body <> ''"
    if args.only_null:
        where += " AND (body_cleaned IS NULL OR body_cleaned = '')"

    sql_select = f"SELECT email_id, body, body_cleaned FROM emails WHERE {where} ORDER BY email_id"
    if args.limit is not None:
        sql_select += f" LIMIT {int(args.limit)}"

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_select)
            rows = cur.fetchall()

        total = len(rows)
        print(f"[backfill] candidates: {total}")
        if args.only_null:
            print("[backfill] mode: only rows with NULL/empty body_cleaned")
        if args.dry_run:
            print("[backfill] DRY RUN — no DB writes")

        t0 = time.time()
        n_changed = 0
        n_recovered = 0
        n_lost = 0
        pending: list[tuple[str | None, str]] = []

        with conn.cursor() as wcur:
            for email_id, body, body_cleaned_old in tqdm(rows, unit="email"):
                new_cleaned = clean_body(body)
                if new_cleaned == body_cleaned_old:
                    continue

                n_changed += 1
                old_empty = not body_cleaned_old
                new_empty = not new_cleaned
                if old_empty and not new_empty:
                    n_recovered += 1
                elif not old_empty and new_empty:
                    n_lost += 1

                pending.append((new_cleaned, str(email_id)))
                if not args.dry_run and len(pending) >= COMMIT_EVERY:
                    wcur.executemany(
                        "UPDATE emails SET body_cleaned = %s WHERE email_id = %s",
                        pending,
                    )
                    conn.commit()
                    pending.clear()

            if pending and not args.dry_run:
                wcur.executemany(
                    "UPDATE emails SET body_cleaned = %s WHERE email_id = %s",
                    pending,
                )
                conn.commit()

    wall = time.time() - t0
    print()
    print(f"[backfill] processed:  {total}")
    print(f"[backfill] changed:    {n_changed}")
    print(f"[backfill] recovered:  {n_recovered}  (NULL/empty -> content)")
    print(f"[backfill] lost:       {n_lost}        (content -> NULL/empty)")
    print(f"[backfill] wall:       {wall:.1f}s")
    if args.dry_run:
        print("[backfill] DRY RUN — nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
