from __future__ import annotations

import psycopg


def next_question_id(conn: psycopg.Connection) -> int:
    row = conn.execute(
        "SELECT question_id FROM ground_truth_v3 ORDER BY question_id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return 1
    try:
        return int(row[0].split("_")[1]) + 1
    except (IndexError, ValueError):
        return 1


def insert_qa(
    conn: psycopg.Connection,
    question_id: str,
    *,
    question: str,
    answer: str,
    category: str,
    source_hint: str | None,
    source_type: str,
    source_id: str,
    chunk_index: int | None,
    voyage_key: str,
    vessel_name: str,
) -> None:
    conn.execute(
        """
        INSERT INTO ground_truth_v3
            (question_id, question, answer, category, source_hint,
             source_type, source_id, chunk_index, voyage_key, vessel_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (question_id) DO NOTHING
        """,
        (
            question_id,
            question,
            answer,
            category,
            source_hint,
            source_type,
            source_id,
            chunk_index,
            voyage_key,
            vessel_name,
        ),
    )
    conn.commit()
