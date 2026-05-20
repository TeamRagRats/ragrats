from __future__ import annotations

from uuid import UUID

import psycopg


def insert_qa(
    conn: psycopg.Connection,
    *,
    question: str,
    answer: str,
    category: str,
    body_cleaned: str,
    structured_md: str | None,
    thread_id: UUID,
    source_id: UUID,
    voyage_key: str,
) -> bool:
    """Insert one ground_truth row. Returns True if inserted, False on conflict."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ground_truth
                (question, category, answer, body_cleaned, structured_md,
                 thread_id, source_id, voyage_key)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id, category) DO NOTHING
            RETURNING question_id
            """,
            (
                question,
                category,
                answer,
                body_cleaned,
                structured_md if structured_md else None,
                thread_id,
                source_id,
                voyage_key,
            ),
        )
        inserted = cur.fetchone() is not None
    conn.commit()
    return inserted
