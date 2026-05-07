from __future__ import annotations

from pathlib import Path

from clients.llm_client import LLMClient

_PROMPT_PATH = Path(__file__).parents[3] / "system_prompts" / "retrieval" / "query_expansion.md"


def _load_system_prompt(n: int) -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").replace("{n}", str(n))


def expand_query(query: str, n: int = 3, llm: LLMClient | None = None) -> list[str]:
    """Returns [original_query, variant_1, ..., variant_n]."""
    if llm is None:
        llm = LLMClient()

    raw = llm.chat(
        system_prompt=_load_system_prompt(n),
        user_prompt=query,
        temperature=0.7,
        max_tokens=400,
    )

    variants = [line.strip() for line in raw.splitlines() if line.strip()][:n]
    return [query] + variants
