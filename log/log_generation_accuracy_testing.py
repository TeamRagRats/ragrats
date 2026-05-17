from __future__ import annotations

import psycopg


def log_generation_accuracy_testing(
    conn: psycopg.Connection,
    *,
    run_id: str,
    question_id: str,
    generated_answer: str,
    ground_truth_answer: str,
    cosine_similarity: float,
    judge_score: int | None,
    judge_reasoning: str | None,
    generation_ms: int,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO test_generation_accuracy_logging
                (run_id, question_id, generated_answer, ground_truth_answer,
                 cosine_similarity, judge_score, judge_reasoning, generation_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                question_id,
                generated_answer,
                ground_truth_answer,
                cosine_similarity,
                judge_score,
                judge_reasoning,
                generation_ms,
            ),
        )
    conn.commit()
