from __future__ import annotations

# Initialises a database from the consolidated schema in sql/db.sql.
#
# Applies the whole file in a single transaction — the core.db connection
# context commits on success and rolls back on any error, so the schema is
# created all-or-nothing. db.sql uses plain CREATE TABLE/SEQUENCE, so this is a
# one-shot bootstrap for an empty database, not a re-runnable migration.
#
# Run standalone: python sql/init_db.py

import sys
from pathlib import Path

if __name__ == "__main__" and __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.db import connect

SCHEMA_FILE = Path(__file__).parent / "db.sql"


def main() -> None:
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    with connect() as conn:
        conn.execute(sql)
    print(f"Applied schema from {SCHEMA_FILE.name} ({len(sql):,} bytes).")


if __name__ == "__main__":
    main()
