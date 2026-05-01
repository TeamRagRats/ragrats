from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).parents[4]
_SYSTEM_PROMPTS_DIR = _REPO_ROOT / "system_prompts" / "summaries"


def _load(name: str) -> str:
    return (_SYSTEM_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


FIXTURE_SUMMARY_SYSTEM = _load("fixture_summary.md")


def build_fixture_summary_prompt(fixture_json: str | dict) -> str:
    if isinstance(fixture_json, dict):
        fixture_text = json.dumps(fixture_json, ensure_ascii=False, indent=2, default=str)
    else:
        fixture_text = str(fixture_json)

    return (
        f"Fixture data:\n{fixture_text}\n\n"
        "Write the summary of this fixture."
    )
