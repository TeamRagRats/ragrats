from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).parents[4]
_SYSTEM_PROMPTS_DIR = _REPO_ROOT / "system_prompts" / "summaries"


def _load(name: str) -> str:
    return (_SYSTEM_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


PHASE_SUMMARY_SYSTEM = _load("phase_summary.md")


def build_phase_summary_prompt(
    voyage_key: str,
    phase_range: str,
    email_summaries: list[dict],
) -> str:
    thread_lines = []
    for i, entry in enumerate(email_summaries, 1):
        status = entry.get("status", "")
        prefix = f"[{i}] {entry['date']}"
        if status:
            prefix += f" ({status})"
        thread_lines.append(f"{prefix}  {entry['summary']}")
    thread_section = "\n".join(thread_lines)

    return (
        f"Voyage: {voyage_key}\n"
        f"Phase: {phase_range}\n\n"
        f"Email thread slice ({len(email_summaries)} emails, chronological):\n"
        f"{thread_section}\n\n"
        "Write the phase summary."
    )
