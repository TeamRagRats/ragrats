from __future__ import annotations

from step_09_summaries.llm_client import LLMClient


def generate_answer(
    client: LLMClient,
    query: str,
    context: str,
    system_prompt: str,
    temperature: float,
    max_tokens: int,
) -> tuple[str, dict[str, int]]:
    user_prompt = (
        "Use the following retrieved context to answer the question.\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"QUESTION:\n{query}"
    )
    return client.chat_with_usage(
        system_prompt,
        user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )
