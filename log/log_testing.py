from __future__ import annotations

import psycopg


def log_retrieval_run(
    conn: psycopg.Connection,
    *,
    run_id: str,
    test_type: str,
    question_type: str,
    top_k: int,
    total: int,
    thread_hits: int,
    thread_recall: float,
    email_hits: int | None = None,
    email_recall: float | None = None,
    strategy: str | None = None,
    lexical: str | None = None,
    reranker: bool = False,
    reformulator: bool = False,
    ef: int | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO test_retrieval_run_logging
                (run_id, test_type, question_type, top_k, total,
                 thread_hits, thread_recall, email_hits, email_recall,
                 strategy, lexical, reranker, reformulator, ef)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (run_id, test_type, question_type, top_k, total,
             thread_hits, thread_recall, email_hits, email_recall,
             strategy, lexical, reranker, reformulator, ef),
        )
    conn.commit()


def log_generation_run(
    conn: psycopg.Connection,
    *,
    run_id: str,
    total: int,
    judge_hits: int,
    avg_cosine: float,
    avg_judge_score: float,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO test_generation_run_logging
                (run_id, total, judge_hits, avg_cosine, avg_judge_score)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (run_id, total, judge_hits, avg_cosine, avg_judge_score),
        )
    conn.commit()
