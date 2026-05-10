from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).parents[4]
_SYSTEM_PROMPTS_DIR = _REPO_ROOT / "system_prompts" / "summaries"


def _load(name: str) -> str:
    return (_SYSTEM_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


EMAIL_SUMMARY_SYSTEM = _load("email_attach_summary.md")


def build_email_summary_prompt(
    direction: str,
    date: str,
    body: str,
    attachments: list[dict],
) -> str:
    attach_block = ""
    if attachments:
        lines = []
        for att in attachments:
            lines.append(f"--- Attachment: {att['filename']} ---")
            lines.append((att.get("content") or "").strip())
        attach_block = "\n\n" + "\n".join(lines)

    return (
        f"Direction: {direction}\n"
        f"Date: {date}\n\n"
        f"Email body:\n{body.strip()}"
        f"{attach_block}\n\n"
        "Summarize this email. Use as many sentences as needed to capture every relevant fact, capped at 10."
    )
