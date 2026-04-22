from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import psycopg

from ..step_02_parse.merge_metadata import EmailRecord

_SQL = """
INSERT INTO emails (
    email_id, voyage_key, thread_id, eml_path, direction, mailbox,
    subject, from_addr, to_addr, sent_at, body_text, body_html,
    body_cleaned, has_attachment, raw_headers, email_json
) VALUES (
    %(email_id)s, %(voyage_key)s, %(thread_id)s, %(eml_path)s, %(direction)s, %(mailbox)s,
    %(subject)s, %(from_addr)s, %(to_addr)s, %(sent_at)s, %(body_text)s, %(body_html)s,
    %(body_cleaned)s, %(has_attachment)s, %(raw_headers)s, %(email_json)s
)
ON CONFLICT (email_id) DO UPDATE SET
    voyage_key     = EXCLUDED.voyage_key,
    thread_id      = EXCLUDED.thread_id,
    eml_path       = EXCLUDED.eml_path,
    direction      = EXCLUDED.direction,
    mailbox        = EXCLUDED.mailbox,
    subject        = EXCLUDED.subject,
    from_addr      = EXCLUDED.from_addr,
    to_addr        = EXCLUDED.to_addr,
    sent_at        = EXCLUDED.sent_at,
    body_text      = EXCLUDED.body_text,
    body_html      = EXCLUDED.body_html,
    body_cleaned   = EXCLUDED.body_cleaned,
    has_attachment = EXCLUDED.has_attachment,
    raw_headers    = EXCLUDED.raw_headers,
    email_json     = EXCLUDED.email_json
"""


def upsert_email(
    cur: psycopg.Cursor, rec: EmailRecord, thread_id, has_attachment: bool, repo_root: Path
) -> None:
    # Store eml_path relative to repo root if possible
    try:
        eml_path = str(rec.eml_path.relative_to(repo_root))
    except ValueError:
        eml_path = str(rec.eml_path)

    cur.execute(
        _SQL,
        {
            "email_id": str(rec.email_id),
            "voyage_key": rec.voyage_key,
            "thread_id": str(thread_id),
            "eml_path": eml_path,
            "direction": rec.direction,
            "mailbox": rec.mailbox,
            "subject": rec.subject,
            "from_addr": rec.from_addr,
            "to_addr": rec.to_addr,
            "sent_at": rec.sent_at,
            "body_text": rec.body_text,
            "body_html": rec.body_html,
            "body_cleaned": rec.body_cleaned,
            "has_attachment": has_attachment,
            "raw_headers": json.dumps(rec.raw_headers),
            "email_json": json.dumps(rec.email_json, default=str),
        },
    )
