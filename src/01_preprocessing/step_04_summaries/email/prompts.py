from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).parents[4]
_SYSTEM_PROMPTS_DIR = _REPO_ROOT / "system_prompts" / "summaries"


def _load(name: str) -> str:
    return (_SYSTEM_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


EMAIL_SUMMARY_SYSTEM = _load("email_body_summary.md")


def build_email_summary_prompt(
    email_id: str,
    thread_id: str,
    voyage_key: str,
    subject: str | None,
    body_cleaned: str | None,
    thread_summary: str | None,
) -> str:
    thread_section = (thread_summary or "").strip() or "(no prior emails in thread)"
    subject_line = subject.strip() if subject else "(no subject)"
    body_section = (body_cleaned or "").strip() or "(no body)"

    return (
        f"Voyage: {voyage_key}\n"
        f"Thread: {thread_id}\n"
        f"Target email: {email_id}\n\n"
        f"Thread context so far:\n{thread_section}\n\n"
        f"Email subject:\n{subject_line}\n\n"
        f"Email body:\n{body_section}\n\n"
        "Write the summary of this email."
    )
