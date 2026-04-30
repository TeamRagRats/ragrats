from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).parents[4]
_SYSTEM_PROMPTS_DIR = _REPO_ROOT / "system_prompts" / "summaries"


def _load(name: str) -> str:
    return (_SYSTEM_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


THREAD_SUMMARY_SYSTEM = _load("thread_summary.md")


def build_thread_summary_prompt(
    thread_id: str,
    voyage_key: str,
    subject: str | None,
    emails: list[dict],
) -> str:
    lines = []
    for i, entry in enumerate(emails, 1):
        to_addrs = ", ".join(entry.get("to_addr") or []) or "unknown"
        lines.append(f"[{i}] {entry['date']}")
        lines.append(f"From: {entry.get('from_addr') or 'unknown'}")
        lines.append(f"To: {to_addrs}")
        lines.append("")
        lines.append(entry.get("summary") or "(no summary)")
        lines.append("")

    thread_section = "\n".join(lines).rstrip()

    subject_line = f"Subject: {subject}\n" if subject else ""
    return (
        f"Voyage: {voyage_key}\n"
        f"Thread: {thread_id}\n"
        f"{subject_line}"
        f"\nEmails ({len(emails)}, chronological):\n\n"
        f"{thread_section}\n\n"
        "Write the thread summary."
    )
