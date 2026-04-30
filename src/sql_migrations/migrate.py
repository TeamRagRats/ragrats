from __future__ import annotations

# Applies pending .sql migration files in filename order, tracking applied files in
# schema_migrations table. Safe to re-run: already-applied files are skipped.
# Run standalone: python src/sql_migrations/migrate.py

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "preprocessing"))

import re

from datetime import datetime, timezone
from pathlib import Path

from shared.db import connect

_DIR = Path(__file__).parent

_ENSURE_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL
)
"""


def main() -> None:
    files = sorted(_DIR.glob("*.sql"))
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_ENSURE_TABLE)
        conn.commit()

        applied = 0
        for f in files:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM schema_migrations WHERE filename = %s", (f.name,))
                if cur.fetchone():
                    print(f"[skip]  {f.name}")
                    continue

            print(f"[apply] {f.name}")
            sql = re.sub(r"--[^\n]*", "", f.read_text())
            statements = [s.strip() for s in sql.split(";") if s.strip()]
            with conn.cursor() as cur:
                for stmt in statements:
                    cur.execute(stmt)
                cur.execute(
                    "INSERT INTO schema_migrations (filename, applied_at) VALUES (%s, %s)",
                    (f.name, datetime.now(timezone.utc)),
                )
            conn.commit()
            applied += 1

    print(f"Done. {applied} migration(s) applied.")


if __name__ == "__main__":
    main()
