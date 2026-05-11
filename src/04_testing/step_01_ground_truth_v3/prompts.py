from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PROMPT_DIR = _REPO_ROOT / "system_prompts" / "ground_truth"


def _load(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8").strip()


_SHARED = _load("_shared_rules.md")

PROMPTS: dict[str, str] = {
    "fact_single":  _load("fact_single.md")  + "\n\n---\n\n" + _SHARED,
    "summary":      _load("summary.md")      + "\n\n---\n\n" + _SHARED,
    "reasoning":    _load("reasoning.md")    + "\n\n---\n\n" + _SHARED,
    "unanswerable": _load("unanswerable.md") + "\n\n---\n\n" + _SHARED,
}


def build_user_message(
    voyage_key: str,
    vessel_name: str,
    chunk_text: str,
    max_chars: int = 3000,
    retry_hint: str | None = None,
) -> str:
    snippet = chunk_text.strip()[:max_chars]
    extra = f"\n\n{retry_hint}" if retry_hint else ""
    return (
        f"Voyage: {voyage_key}\n"
        f"Vessel: {vessel_name}\n"
        f"\nCHUNK:\n{snippet}\n"
        f"\nYour question MUST contain the exact phrase \"{vessel_name}\". "
        f"A question that does not include this phrase will be rejected."
        f"{extra}"
    )
