"""
Writes validated Q&A pairs to ground_truth_v2.

next_question_id()  : reads highest existing ID and returns the next one
insert_qa()         : inserts one row and commits immediately
"""
from __future__ import annotations

import psycopg


def next_question_id(conn: psycopg.Connection) -> int:
    row = conn.execute(
        "SELECT question_id FROM ground_truth_v2 ORDER BY question_id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return 1
    # format: gt2_0001
    try:
        return int(row[0].split("_")[1]) + 1
    except (IndexError, ValueError):
        return 1


def insert_qa(
    conn: psycopg.Connection,
    question_id: str,
    question: str,
    answer: str,
    category: str,
    difficulty: str,
    source_type: str,
    source_id: str | None,
    source_chunk_id: str,
    voyage_key: str,
    vessel_name: str,
) -> None:
    conn.execute(
        """
        INSERT INTO ground_truth_v2 (
            question_id, question, ground_truth_answer, category, difficulty,
            source_type, source_id, source_chunk_id, voyage_key, vessel_name
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (question_id) DO NOTHING
        """,
        (
            question_id,
            question,
            answer,
            category,
            difficulty,
            source_type,
            source_id or None,
            source_chunk_id,
            voyage_key,
            vessel_name,
        ),
    )
    conn.commit()
