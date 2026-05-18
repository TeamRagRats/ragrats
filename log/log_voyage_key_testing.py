from __future__ import annotations

import json

import psycopg


def log_voyage_key_testing(
    conn: psycopg.Connection,
    *,
    run_id: str,
    question_id: str,
    top_k: int,
    expected_key: str,
    returned_keys: list[str],
    hit: bool,
    winner_rank: int | None,
    vote_counts: dict[str, int],
) -> None:
    """Logs a single question result to the test_retrieval_vk_logging table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO test_retrieval_vk_logging
                (run_id, question_id, top_k, expected_key, returned_keys, hit, winner_rank, vote_counts)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                question_id,
                top_k,
                expected_key,
                returned_keys,
                hit,
                winner_rank,
                json.dumps(vote_counts),
            ),
        )
    conn.commit()
