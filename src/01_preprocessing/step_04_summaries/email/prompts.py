from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).parents[4]
_SYSTEM_PROMPTS_DIR = _REPO_ROOT / "system_prompts" / "summaries"


def _load(name: str) -> str:
    return (_SYSTEM_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


EMAIL_SUMMARY_SYSTEM = _load("email_summary.md")


def build_email_summary_prompt(
    subject: str | None,
    body_cleaned: str | None,
    thread_summary: str | None,
    from_addr: str | None,
    to_addr: list[str] | None,
) -> str:
    thread_section = (thread_summary or "").strip() or "(no prior emails in thread)"
    subject_line = subject.strip() if subject else "(no subject)"
    body_section = (body_cleaned or "").strip() or "(no body)"
    from_line = (from_addr or "").strip() or "unknown"
    to_line = ", ".join(to_addr or []) or "unknown"

    return (
        f"Thread context so far:\n{thread_section}\n\n"
        f"From: {from_line}\n"
        f"To: {to_line}\n"
        f"Subject: {subject_line}\n\n"
        f"Email body:\n{body_section}\n\n"
        "Write the summary of this email."
    )
