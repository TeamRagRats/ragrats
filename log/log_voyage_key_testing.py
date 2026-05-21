from __future__ import annotations

import json

import psycopg


def log_voyage_key_testing(
    conn: psycopg.Connection,
    *,
    run_id: str,
    question_id: str,
    category: str,
    question: str,
    expected_key: str,
    returned_keys: list[str],
    hit: bool,
    winner_rank: int | None,
    vote_counts: dict[str, int],
    chunks: list[dict],
    flags: dict,
) -> None:
    """Logs a single question result to the test_retrieval_vk_logging table.

    chunks: retrieved candidate-chunk metadata (no text). flags: the CLI flags
    the run used. Both stored as JSONB so the run is self-describing.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO test_retrieval_vk_logging
                (run_id, question_id, category, question, expected_key,
                 returned_keys, hit, winner_rank, vote_counts, chunks, flags)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                question_id,
                category,
                question,
                expected_key,
                returned_keys,
                hit,
                winner_rank,
                json.dumps(vote_counts),
                json.dumps(chunks),
                json.dumps(flags),
            ),
        )
    conn.commit()
