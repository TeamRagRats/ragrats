from __future__ import annotations

import psycopg


def fetch_fixture_summaries(
    conn: psycopg.Connection,
    voyage_keys: list[str],
) -> dict[str, str]:
    """voyage_key -> fixture summary text. Skips rows with status != 'ok'."""
    if not voyage_keys:
        return {}
    rows = conn.execute(
        """
        SELECT voyage_key, summary
        FROM fixture_summaries
        WHERE voyage_key = ANY(%s)
          AND status = 'ok'
          AND summary <> ''
        """,
        [list(set(voyage_keys))],
    ).fetchall()
    return {voyage_key: summary for voyage_key, summary in rows}
