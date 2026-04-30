from __future__ import annotations

from uuid import UUID
import psycopg

def log_generation(
    conn: psycopg.Connection,
    *,
    retrieval_run_id: str | UUID | None,
    query: str,
    answer: str,
    system_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    prompt_tokens: int,
    completion_tokens: int,
    generation_ms: int,
    total_ms: int,
) -> None:
    """Logs a generation run to the database."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO generation_logging
                (retrieval_run_id, query, answer, system_prompt, model, temperature,
                 max_tokens, prompt_tokens, completion_tokens, generation_ms, total_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(retrieval_run_id) if retrieval_run_id else None,
                query,
                answer,
                system_prompt,
                model,
                temperature,
                max_tokens,
                prompt_tokens,
                completion_tokens,
                generation_ms,
                total_ms,
            ),
        )
    conn.commit()
