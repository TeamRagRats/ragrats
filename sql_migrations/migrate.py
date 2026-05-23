from __future__ import annotations

# Applies pending .sql migration files in filename order, tracking applied files in
# schema_migrations table. Safe to re-run: already-applied files are skipped.
# Run standalone: python sql_migrations/migrate.py

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _repo_root = _Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_repo_root / "src" / "01_preprocessing"))

import re

from datetime import datetime, timezone
from pathlib import Path

from core.db import connect

_DIR = Path(__file__).parent

_ENSURE_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL
)
"""


_DOLLAR_TAG = re.compile(r"\$[A-Za-z_][A-Za-z_0-9]*\$|\$\$")


def _split_statements(sql: str) -> list[str]:
    """Split SQL on top-level semicolons, respecting dollar-quoted blocks
    (e.g. ``DO $$ ... $$;``) and single-quoted string literals so we don't
    chop a multi-statement PL/pgSQL block in half."""
    statements: list[str] = []
    buf: list[str] = []
    i = 0
    dollar_tag: str | None = None
    in_single = False
    while i < len(sql):
        ch = sql[i]
        if dollar_tag is not None:
            if sql.startswith(dollar_tag, i):
                buf.append(dollar_tag)
                i += len(dollar_tag)
                dollar_tag = None
                continue
            buf.append(ch)
            i += 1
            continue
        if in_single:
            buf.append(ch)
            i += 1
            if ch == "'":
                if i < len(sql) and sql[i] == "'":
                    buf.append("'")
                    i += 1
                else:
                    in_single = False
            continue
        if ch == "'":
            in_single = True
            buf.append(ch)
            i += 1
            continue
        if ch == "$":
            m = _DOLLAR_TAG.match(sql, i)
            if m:
                dollar_tag = m.group(0)
                buf.append(dollar_tag)
                i += len(dollar_tag)
                continue
        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


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
            statements = _split_statements(sql)
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
