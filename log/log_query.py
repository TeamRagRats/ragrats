from __future__ import annotations
import psycopg


def log_query(conn: psycopg.Connection, query_text: str, source: str, username: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO queries (query_text, source, username)
            VALUES (%s, %s, %s)
            RETURNING query_id
            """,
            (query_text, source, username),
        )
        row = cur.fetchone()
        conn.commit()
        return str(row[0])
