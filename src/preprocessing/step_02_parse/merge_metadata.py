from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from .parse_eml import AttachmentPart, ParsedEml


@dataclass
class EmailRecord:
    email_id: UUID
    voyage_key: str
    eml_path: Path
    direction: str
    mailbox: str | None
    subject: str | None
    from_addr: str | None
    to_addr: list[str]
    cc_addr: list[str]
    sent_at: datetime | None
    message_id: str | None
    in_reply_to: str | None
    references: list[str]
    body_text: str | None
    body_html: str | None
    body_cleaned: str | None
    raw_headers: dict[str, Any]
    email_json: dict[str, Any]
    attachments: list[AttachmentPart] = field(default_factory=list)


def _direction(json_dir: str | None, fallback: str) -> str:
    if json_dir == "Incoming":
        return "in"
    if json_dir == "Outgoing":
        return "out"
    return fallback


def _mailbox(sidecar: dict[str, Any]) -> str | None:
    mailboxes = sidecar.get("Mailboxes") or []
    if mailboxes and isinstance(mailboxes, list):
        first = mailboxes[0]
        if isinstance(first, dict):
            return first.get("Name")
    return None


def _clean_header(val: Any) -> str | None:
    if not val:
        return None
    s = str(val).strip()
    return s if s else None


def _parse_references(val: Any) -> list[str]:
    if not val:
        return []
    # References are usually space-separated Message-IDs
    return [r.strip() for r in str(val).split() if r.strip()]


def merge_metadata(
    voyage_key: str,
    eml_path: Path,
    direction_fallback: str,
    parsed: ParsedEml,
    sidecar: dict[str, Any],
) -> EmailRecord:
    email_id = UUID(sidecar["DocumentGid"])
    headers = parsed.raw_headers
    return EmailRecord(
        email_id=email_id,
        voyage_key=voyage_key,
        eml_path=eml_path,
        direction=_direction(sidecar.get("Direction"), direction_fallback),
        mailbox=_mailbox(sidecar),
        subject=parsed.subject,
        from_addr=parsed.from_addr,
        to_addr=parsed.to_addr,
        cc_addr=parsed.cc_addr,
        sent_at=parsed.sent_at,
        message_id=_clean_header(headers.get("Message-ID")),
        in_reply_to=_clean_header(headers.get("In-Reply-To")),
        references=_parse_references(headers.get("References")),
        body_text=parsed.body_text,
        body_html=parsed.body_html,
        body_cleaned=None,
        raw_headers=headers,
        email_json=sidecar,
        attachments=parsed.attachments,
    )
