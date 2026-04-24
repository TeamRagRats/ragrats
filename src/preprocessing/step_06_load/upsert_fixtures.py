from __future__ import annotations

# Bulk-upserts fixture rows (from the ARC_FIXTURES xlsx) into the fixtures table.
# Dynamically builds the INSERT from column names so schema changes in the xlsx are picked up.
# Called once at the start of run_ingest.py.

import psycopg


def upsert_fixtures(cur: psycopg.Cursor, rows: list[dict]) -> int:
    if not rows:
        return 0

    cols = list(rows[0].keys())
    col_list = ", ".join(cols)
    val_list = ", ".join(f"%({c})s" for c in cols)
    update_set = ",\n        ".join(
        f"{c} = EXCLUDED.{c}" for c in cols if c != "voyage_key"
    ) + ",\n        loaded_at = NOW()"

    sql = f"""
INSERT INTO fixtures ({col_list})
VALUES ({val_list})
ON CONFLICT (voyage_key) DO UPDATE SET
        {update_set}
"""
    for row in rows:
        cur.execute(sql, row)
    return len(rows)
