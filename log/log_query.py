from __future__ import annotations
import psycopg


def get_developer_user_id(conn: psycopg.Connection) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT user_id FROM users WHERE username = 'developer'")
        row = cur.fetchone()
        if row is None:
            raise RuntimeError("Developer user not found in users table. Run migrations first.")
        return str(row[0])


def log_query(conn: psycopg.Connection, query_text: str, source: str, user_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO queries (query_text, source, user_id)
            VALUES (%s, %s, %s)
            RETURNING query_id
            """,
            (query_text, source, user_id),
        )
        row = cur.fetchone()
        conn.commit()
        return str(row[0])
