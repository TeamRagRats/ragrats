from __future__ import annotations

import re
from dataclasses import dataclass

import psycopg

_TRAILING_NUM = re.compile(r"^(.+)_(\d+)$")


def vessel_name_from_key(voyage_key: str) -> str:
    m = _TRAILING_NUM.match(voyage_key)
    base = m.group(1) if m else voyage_key
    return base.replace("_", " ").title()


def list_voyage_keys(conn: psycopg.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT voyage_key FROM chunks ORDER BY voyage_key"
    ).fetchall()
    return [r[0] for r in rows]


@dataclass
class EmailRow:
    email_id: str
    voyage_key: str
    vessel_name: str
    body_cleaned: str


@dataclass
class AttachmentChunkRow:
    chunk_id: str
    source_id: str
    chunk_index: int
    voyage_key: str
    vessel_name: str
    text: str


def sample_emails(
    conn: psycopg.Connection,
    voyage_key: str,
    limit: int,
) -> list[EmailRow]:
    rows = conn.execute(
        """
        SELECT email_id, voyage_key, body_cleaned
        FROM emails
        WHERE voyage_key = %s
          AND body_cleaned IS NOT NULL
          AND body_cleaned <> ''
        ORDER BY random()
        LIMIT %s
        """,
        (voyage_key, limit),
    ).fetchall()
    vessel_name = vessel_name_from_key(voyage_key)
    return [
        EmailRow(
            email_id=str(r[0]),
            voyage_key=r[1],
            vessel_name=vessel_name,
            body_cleaned=r[2],
        )
        for r in rows
    ]


def sample_attachment_chunks(
    conn: psycopg.Connection,
    voyage_key: str,
    limit: int,
) -> list[AttachmentChunkRow]:
    rows = conn.execute(
        """
        SELECT chunk_id, source_id, chunk_index, voyage_key, text
        FROM chunks
        WHERE strategy    = 'plain'
          AND source_type = 'attachment'
          AND voyage_key  = %s
          AND text IS NOT NULL
          AND text <> ''
        ORDER BY random()
        LIMIT %s
        """,
        (voyage_key, limit),
    ).fetchall()
    vessel_name = vessel_name_from_key(voyage_key)
    return [
        AttachmentChunkRow(
            chunk_id=str(r[0]),
            source_id=str(r[1]),
            chunk_index=r[2],
            voyage_key=r[3],
            vessel_name=vessel_name,
            text=r[4] or "",
        )
        for r in rows
    ]
