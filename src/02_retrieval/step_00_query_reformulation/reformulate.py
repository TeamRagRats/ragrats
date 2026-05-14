from __future__ import annotations

import logging
from pathlib import Path

from clients.llm_client import LLMClient

_logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    Path(__file__).parents[3] / "system_prompts" / "reformulation" / "rewrite.md"
).read_text(encoding="utf-8").strip()


def reformulate_query(llm: LLMClient, query: str) -> str:
    rewritten = llm.chat(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=query,
        temperature=0.1,
        max_tokens=256,
    )
    if rewritten and rewritten != query:
        _logger.info("Query reformulated: %r → %r", query, rewritten)
    return rewritten or query
