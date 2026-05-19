from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PROMPT_DIR = _REPO_ROOT / "system_prompts" / "ground_truth"


def _load(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8").strip()


_SHARED = _load("_shared_rules.md")

PROMPTS: dict[str, str] = {
    "fact_single":  _load("fact_single.md")  + "\n\n---\n\n" + _SHARED,
    "reasoning":    _load("reasoning.md")    + "\n\n---\n\n" + _SHARED,
    "summary":      _load("summary.md")      + "\n\n---\n\n" + _SHARED,
    "unanswerable": _load("unanswerable.md") + "\n\n---\n\n" + _SHARED,
}


def build_user_message(
    *,
    voyage_key: str,
    vessel_name: str,
    body_cleaned: str,
    structured_md: str | None,
    operator_query_examples: list[str],
    max_body_chars: int = 4000,
    max_structured_chars: int = 4000,
    retry_hint: str | None = None,
) -> str:
    body = (body_cleaned or "").strip()[:max_body_chars]
    structured = (structured_md or "").strip()[:max_structured_chars]

    examples_block = ""
    if operator_query_examples:
        bullets = "\n".join(f"- {q.strip()}" for q in operator_query_examples if q.strip())
        examples_block = (
            "\nREAL OPERATOR QUERIES (style references — match the tone and phrasing, "
            "do NOT copy verbatim, do NOT answer them):\n"
            f"{bullets}\n"
        )

    structured_block = ""
    if structured:
        structured_block = f"\nSTRUCTURED CONTEXT:\n{structured}\n"

    extra = f"\n\n{retry_hint}" if retry_hint else ""

    return (
        f"Voyage: {voyage_key}\n"
        f"Vessel: {vessel_name}\n"
        f"\nEMAIL BODY:\n{body}\n"
        f"{structured_block}"
        f"{examples_block}"
        f"\nYour question MUST contain the exact phrase \"{vessel_name}\". "
        f"A question that does not include this phrase will be rejected."
        f"{extra}"
    )
