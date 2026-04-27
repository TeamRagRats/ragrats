from __future__ import annotations

# Loads system prompt markdown files from system_prompts/ at import time and provides
# user prompt builder functions for each summary type (email, fixture, phase, voyage).
# Used by email_summaries.py and voyage_summaries.py.

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).parents[3]
_SYSTEM_PROMPTS_DIR = _REPO_ROOT / "system_prompts"


def _load(name: str) -> str:
    return (_SYSTEM_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


EMAIL_SUMMARY_SYSTEM = _load("summaries/email_summary.md")
FIXTURE_SUMMARY_SYSTEM = _load("summaries/fixture_summary.md")
PHASE_SUMMARY_SYSTEM = _load("summaries/phase_summary.md")
VOYAGE_SUMMARY_SYSTEM = _load("summaries/voyage_summary.md")


# ---------------------------------------------------------------------------
# User prompt builders
# ---------------------------------------------------------------------------

_SEP = "-" * 50


def build_email_summary_prompt(
    direction: str,
    date: str,
    body: str,
    attachments: list[dict],
    from_addr: str = "UNKNOWN",
) -> str:
    dir_label = (direction or "UNKNOWN").upper()
    lines = [
        _SEP,
        f"EMAIL {dir_label} FROM {from_addr} [{date}]:",
        "",
        body.strip(),
    ]
    for i, att in enumerate(attachments, 1):
        doc_type = att.get("document_type") or "UNKNOWN"
        lines += [
            "",
            _SEP,
            f"ATTACHMENT {i}: {att['filename']}",
            f"{doc_type} + ATTACHMENT STRUCTURED",
            "",
            (att.get("content") or "").strip(),
        ]
    return "\n".join(lines)


def build_fixture_summary_prompt(fixture_json: str | dict) -> str:
    if isinstance(fixture_json, dict):
        fixture_text = json.dumps(fixture_json, ensure_ascii=False, indent=2)
    else:
        fixture_text = str(fixture_json)

    return (
        f"Fixture data:\n{fixture_text}\n\n"
        "Write a 3–5 sentence summary of this fixture."
    )


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
        "Write a detailed phase summary (~1500-2000 tokens)."
    )


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
