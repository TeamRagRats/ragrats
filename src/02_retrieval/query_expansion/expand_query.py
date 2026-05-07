from __future__ import annotations

import json
import re

from clients.llm_client import LLMClient


_SYSTEM_PROMPT = """You are a query reformulation engine for a maritime RAG system.

Your job: given a user question (and optional recent conversation), produce a JSON array of 4 search queries that will be used to retrieve passages from a corpus of maritime operations documents (SMS, fixtures, voyage emails, charter party documents).

Rules:
- The first element MUST be the user's question rewritten as a standalone, context-resolved English query (resolve pronouns and follow-ups using the conversation history).
- The remaining 3 elements are diverse paraphrases that vary terminology, specificity, and angle:
    * one using formal maritime / regulatory terminology (SOLAS, MARPOL, ISM, charter party, laytime, etc. where applicable)
    * one using operational / practical phrasing as it might appear in an email or report
    * one focused on the specific entities or events mentioned (vessel, port, cargo, person)
- All queries in English, regardless of input language.
- Each query is a single sentence or noun phrase, no more than 25 words.
- Do not invent facts not implied by the question or history.
- Output ONLY a JSON array of 4 strings. No prose, no markdown fence, no explanation."""


def _build_user_prompt(query: str, history: list[tuple[str, str]]) -> str:
    if not history:
        return f"User question: {query}\n\nReturn the JSON array."

    lines = ["Recent conversation (oldest first):"]
    for q, a in history:
        lines.append(f"Q: {q}")
        if a:
            snippet = a if len(a) <= 300 else a[:300] + "…"
            lines.append(f"A: {snippet}")
    lines.append("")
    lines.append(f"Current user question: {query}")
    lines.append("")
    lines.append("Return the JSON array.")
    return "\n".join(lines)


def _parse_variants(raw: str, original: str) -> list[str]:
    text = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return [original]
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return [original]

    if not isinstance(data, list):
        return [original]

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if not s or s.lower() in seen:
            continue
        seen.add(s.lower())
        cleaned.append(s)

    return cleaned or [original]


def expand_query(
    llm: LLMClient,
    query: str,
    history: list[tuple[str, str]] | None = None,
    max_variants: int = 4,
    temperature: float = 0.4,
) -> list[str]:
    """
    Returns a list of search-query variants for the given user query.
    On any failure, falls back to [query]. Result always contains the original
    (or its rewritten form) as the first element.
    """
    user_prompt = _build_user_prompt(query, history or [])
    try:
        raw = llm.chat(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=400,
        )
    except Exception:
        return [query]

    variants = _parse_variants(raw, query)
    return variants[:max_variants] if variants else [query]
