from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).parents[4]
_SYSTEM_PROMPTS_DIR = _REPO_ROOT / "system_prompts" / "summaries"


def _load(name: str) -> str:
    return (_SYSTEM_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


EMAIL_THREAD_SUMMARY_SYSTEM = _load("email_thread_summary.md")


def build_email_thread_summary_prompt(
    email_id: str,
    thread_id: str,
    voyage_key: str,
    subject: str | None,
    prior_emails: list[dict],
) -> str:
    lines = []
    for i, entry in enumerate(prior_emails, 1):
        to_addrs = ", ".join(entry.get("to_addr") or []) or "unknown"
        lines.append(f"[{i}] {entry['date']}")
        lines.append(f"From: {entry.get('from_addr') or 'unknown'}")
        lines.append(f"To: {to_addrs}")
        lines.append("")
        lines.append(entry.get("body_cleaned") or "(no body)")
        lines.append("")

    prior_section = "\n".join(lines).rstrip()

    subject_line = f"Subject: {subject}\n" if subject else ""
    return (
        f"Voyage: {voyage_key}\n"
        f"Thread: {thread_id}\n"
        f"Target email: {email_id}\n"
        f"{subject_line}"
        f"\nPrior emails ({len(prior_emails)}, chronological):\n\n"
        f"{prior_section}\n\n"
        "Write the summary of the thread so far, up to but excluding the target email."
    )
