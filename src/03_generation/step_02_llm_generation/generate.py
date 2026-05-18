from __future__ import annotations

from clients.llm_client import LLMClient


def generate_answer(
    client: LLMClient,
    query: str,
    context: str,
    system_prompt: str,
    temperature: float,
    max_tokens: int,
) -> tuple[str, dict[str, int], str]:
    """Returns (answer, usage, user_prompt). The user prompt is returned so
    callers can persist the exact text the LLM received (CONTEXT + QUESTION)."""
    user_prompt = (
        "Use the following retrieved context to answer the question.\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"QUESTION:\n{query}"
    )
    answer, usage = client.chat_with_usage(
        system_prompt,
        user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return answer, usage, user_prompt
