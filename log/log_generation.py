from __future__ import annotations

import psycopg

def log_generation(
    conn: psycopg.Connection,
    *,
    query_id: str,
    query_text: str,
    answer: str,
    system_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    prompt_tokens: int,
    completion_tokens: int,
    generation_ms: int,
    total_ms: int,
    llm_input: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO generation_logging
                (query_id, query_text, answer, system_prompt, model, temperature,
                 max_tokens, prompt_tokens, completion_tokens, generation_ms, total_ms,
                 llm_input)
            VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                query_id,
                query_text,
                answer,
                system_prompt,
                model,
                temperature,
                max_tokens,
                prompt_tokens,
                completion_tokens,
                generation_ms,
                total_ms,
                llm_input,
            ),
        )
    conn.commit()
