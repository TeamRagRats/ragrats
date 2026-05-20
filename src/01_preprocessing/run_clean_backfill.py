from __future__ import annotations

# Recomputes emails.body_cleaned from the already-stored body_text by re-running
# clean_body. Use after changing any rule in step_01_ingest/clean/* so existing
# rows pick up the new cleaning without a full re-ingest from .eml files.
#
# Re-embedding is still required afterwards for chunks to reflect the new text.
#
# Run from this directory: python run_clean_backfill.py [--limit N] [--dry-run]

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _repo_root = _here.parents[1]
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_here))
    __package__ = "src.01_preprocessing"

import argparse

from core.db import connect

from step_01_ingest.clean import clean_body

_BATCH = 500


def _iter_emails(conn, limit: int | None):
    sql = "SELECT email_id, body_text, body_cleaned FROM emails ORDER BY email_id"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql).fetchall()


def main() -> None:
    p = argparse.ArgumentParser(description="Backfill emails.body_cleaned from body_text")
    p.add_argument("--limit", type=int, default=None, metavar="N",
                   help="Behandl kun de første N emails (til test)")
    p.add_argument("--dry-run", action="store_true",
                   help="Beregn og rapportér ændringer uden at skrive til DB")
    args = p.parse_args()

    with connect() as conn:
        rows = _iter_emails(conn, args.limit)
        total = len(rows)
        changed = 0
        pending: list[tuple[str | None, str]] = []

        with conn.cursor() as cur:
            for email_id, body_text, current in rows:
                new = clean_body(body_text)
                if new == current:
                    continue
                changed += 1
                if args.dry_run:
                    continue
                pending.append((new, str(email_id)))
                if len(pending) >= _BATCH:
                    cur.executemany(
                        "UPDATE emails SET body_cleaned = %s WHERE email_id = %s",
                        pending,
                    )
                    conn.commit()
                    pending.clear()

            if pending:
                cur.executemany(
                    "UPDATE emails SET body_cleaned = %s WHERE email_id = %s",
                    pending,
                )
                conn.commit()

    verb = "ville ændre" if args.dry_run else "ændrede"
    print(f"{verb} {changed}/{total} emails.body_cleaned")


if __name__ == "__main__":
    main()
