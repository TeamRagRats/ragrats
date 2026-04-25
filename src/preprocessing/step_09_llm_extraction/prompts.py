from __future__ import annotations

# Loads the two LLM extraction system prompts from system_prompts/llm_extraction/.
# FULL  → document_restructuring.md (small/medium/large; output 8 196 tokens)
# CLASSIFY → document_classification.md (huge; truncated input, ~50-token output)

from pathlib import Path

_REPO_ROOT = Path(__file__).parents[3]
_PROMPTS_DIR = _REPO_ROOT / "system_prompts" / "llm_extraction"


def _load(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


FULL_SYSTEM_PROMPT     = _load("document_restructuring.md")
CLASSIFY_SYSTEM_PROMPT = _load("document_classification.md")
