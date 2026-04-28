from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).parents[4]
_SYSTEM_PROMPTS_DIR = _REPO_ROOT / "system_prompts" / "summaries"


def _load(name: str) -> str:
    return (_SYSTEM_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


VOYAGE_SUMMARY_SYSTEM = _load("voyage_summary.md")


def build_voyage_summary_from_phases_prompt(
    voyage_key: str,
    fixture_paragraph: str | None,
    phases: list[dict],
) -> str:
    fixture_section = (
        f"Fixture:\n{fixture_paragraph.strip()}\n"
        if fixture_paragraph
        else "Fixture: (no fixture data available)\n"
    )

    phase_lines = []
    for i, p in enumerate(phases, 1):
        date_range = ""
        if p.get("date_start") or p.get("date_end"):
            date_range = f" [{p.get('date_start','?')} - {p.get('date_end','?')}]"
        header = (
            f"=== Phase {i}/{len(phases)}: {p.get('phase_range','')}"
            f"{date_range} ({p.get('email_count', 0)} emails) ==="
        )
        phase_lines.append(header)
        phase_lines.append((p.get("summary") or "").strip())
        phase_lines.append("")
    phases_section = "\n".join(phase_lines)

    return (
        f"Voyage: {voyage_key}\n\n"
        f"{fixture_section}\n"
        f"Phase summaries ({len(phases)} phases, chronological):\n"
        f"{phases_section}\n\n"
        "Write a comprehensive voyage narrative that integrates all phases "
        "into a single coherent story."
    )
