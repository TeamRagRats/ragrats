from __future__ import annotations

from clients.llm_client import LLMClient

_SYSTEM = """\
You are a shipping operations assistant.
Given a question about shipping operations, write a short passage (2-4 sentences) \
that directly answers the question, as if it were extracted from a shipping email, \
voyage fixture, or operational report.
Use specific shipping terminology and realistic details. \
Do not say you don't know — always generate a plausible factual answer."""


def generate_hyde(client: LLMClient, question: str) -> str:
    """Generate a hypothetical document passage that answers the question.
    The resulting text embeds closer to the real answer chunk than the question itself."""
    return client.chat(
        system_prompt=_SYSTEM,
        user_prompt=question,
        temperature=0.3,
        max_tokens=150,
    )
