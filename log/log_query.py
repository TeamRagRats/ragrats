from __future__ import annotations
import psycopg


def log_query(
    conn: psycopg.Connection,
    query_text: str,
    source: str,
    username: str,
    session_id: str | None = None,
) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO queries (query_text, source, username, session_id)
            VALUES (%s, %s, %s, %s::uuid)
            RETURNING query_id
            """,
            (query_text, source, username, session_id),
        )
        row = cur.fetchone()
        conn.commit()
        return str(row[0])
