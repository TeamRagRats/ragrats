from __future__ import annotations

# Parses a .eml file into a ParsedEml dataclass (subject, addresses, body text/html, attachments).
# Defines the AttachmentPart dataclass used downstream by extract_attachments.py.
# Consumed by merge_metadata.py.

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any


@dataclass
class AttachmentPart:
    file_name: str
    mime_type: str
    payload: bytes


@dataclass
class ParsedEml:
    subject: str | None
    from_addr: str | None
    to_addr: list[str]
    cc_addr: list[str]
    sent_at: datetime | None
    body_text: str | None
    body_html: str | None
    attachments: list[AttachmentPart] = field(default_factory=list)
    raw_headers: dict[str, Any] = field(default_factory=dict)


def _addresses(msg: EmailMessage, header: str) -> list[str]:
    values = msg.get_all(header, [])
    return [a for _, a in getaddresses(values) if a]


def _parse_sent_at(msg: EmailMessage) -> datetime | None:
    date_hdr = msg.get("Date")
    if not date_hdr:
        return None
    dt = parsedate_to_datetime(date_hdr)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _body_parts(msg: EmailMessage) -> tuple[str | None, str | None]:
    body_text: str | None = None
    body_html: str | None = None
    text_part = msg.get_body(preferencelist=("plain",))
    html_part = msg.get_body(preferencelist=("html",))
    if text_part is not None:
        body_text = text_part.get_content()
    if html_part is not None:
        body_html = html_part.get_content()
    return body_text, body_html


def _collect_attachments(msg: EmailMessage) -> list[AttachmentPart]:
    out: list[AttachmentPart] = []
    for part in msg.iter_attachments():
        name = part.get_filename() or "attachment.bin"
        mime = part.get_content_type()
        raw = part.get_payload(decode=True)
        payload: bytes = bytes(raw) if isinstance(raw, (bytes, bytearray)) else b""
        out.append(AttachmentPart(file_name=name, mime_type=mime, payload=payload))
    return out


def parse_eml(eml_path: Path) -> ParsedEml:
    with eml_path.open("rb") as f:
        msg: EmailMessage = BytesParser(policy=policy.default).parse(f)
    body_text, body_html = _body_parts(msg)
    raw_headers = {k: str(v) for k, v in msg.items()}
    return ParsedEml(
        subject=msg.get("Subject"),
        from_addr=(_addresses(msg, "From") or [None])[0],
        to_addr=_addresses(msg, "To"),
        cc_addr=_addresses(msg, "Cc"),
        sent_at=_parse_sent_at(msg),
        body_text=body_text,
        body_html=body_html,
        attachments=_collect_attachments(msg),
        raw_headers=raw_headers,
    )


if __name__ == "__main__":
    import sys

    parsed = parse_eml(Path(sys.argv[1]))
    print("subject:", parsed.subject)
    print("from:", parsed.from_addr)
    print("to:", parsed.to_addr)
    print("sent_at:", parsed.sent_at)
    print("attachments:", [(a.file_name, a.mime_type, len(a.payload)) for a in parsed.attachments])
