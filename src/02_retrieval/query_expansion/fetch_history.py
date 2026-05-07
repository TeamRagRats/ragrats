from __future__ import annotations

import psycopg


def fetch_session_history(
    conn: psycopg.Connection,
    session_id: str | None,
    max_turns: int = 3,
) -> list[tuple[str, str]]:
    """
    Returns up to `max_turns` most recent (question, answer) pairs for the given
    session, ordered oldest -> newest. Empty list if session_id is None or no history.
    """
    if not session_id:
        return []

    rows = conn.execute(
        """
        SELECT q.query_text, COALESCE(gl.answer, '')
        FROM queries q
        LEFT JOIN generation_logging gl ON gl.query_id = q.query_id
        WHERE q.session_id = %s::uuid
        ORDER BY q.created_at DESC
        LIMIT %s
        """,
        (session_id, max_turns),
    ).fetchall()

    return [(row[0], row[1]) for row in reversed(rows)]
