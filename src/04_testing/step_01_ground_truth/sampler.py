from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

import psycopg


_MIN_BODY_CHARS = 100
_EMAILS_PER_VOYAGE = 2
_MAX_ATTACHMENTS = 3


@dataclass
class EmailSample:
    email_id: UUID
    thread_id: UUID
    voyage_key: str
    body_cleaned: str
    structured_md: str  # concat of up to 3 attachments' structured_md, "" if none


def list_voyage_keys(conn: psycopg.Connection, limit: int | None = None) -> list[str]:
    sql = "SELECT voyage_key FROM fixtures ORDER BY voyage_key"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    with conn.cursor() as cur:
        cur.execute(sql)
        return [r[0] for r in cur.fetchall()]


def get_vessel_name(conn: psycopg.Connection, voyage_key: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT vessel_name FROM fixtures WHERE voyage_key = %s",
            (voyage_key,),
        )
        row = cur.fetchone()
    return row[0] if row and row[0] else None


def pick_emails_for_voyage(
    conn: psycopg.Connection,
    voyage_key: str,
    limit: int = _EMAILS_PER_VOYAGE,
) -> list[EmailSample]:
    """Two earliest emails for the voyage with non-trivial body_cleaned."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT email_id, thread_id, body_cleaned
            FROM emails
            WHERE voyage_key = %s
              AND body_cleaned IS NOT NULL
              AND length(body_cleaned) > %s
            ORDER BY sent_at ASC NULLS LAST, email_id ASC
            LIMIT %s
            """,
            (voyage_key, _MIN_BODY_CHARS, limit),
        )
        rows = cur.fetchall()

    samples: list[EmailSample] = []
    for email_id, thread_id, body_cleaned in rows:
        structured = _fetch_structured_md(conn, email_id)
        samples.append(
            EmailSample(
                email_id=email_id,
                thread_id=thread_id,
                voyage_key=voyage_key,
                body_cleaned=body_cleaned,
                structured_md=structured,
            )
        )
    return samples


def _fetch_structured_md(conn: psycopg.Connection, email_id: UUID) -> str:
    """Concatenate up to 3 attachments' structured_md for this email."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ls.structured_md
            FROM attachments a
            JOIN llm_structured ls ON ls.sha256 = a.sha256
            WHERE a.email_id = %s
              AND ls.structured_md IS NOT NULL
              AND length(ls.structured_md) > 0
            ORDER BY a.sha256
            LIMIT %s
            """,
            (email_id, _MAX_ATTACHMENTS),
        )
        parts = [r[0] for r in cur.fetchall() if r[0]]
    return "\n\n---\n\n".join(parts)


def sample_operator_queries(conn: psycopg.Connection, n: int = 8) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT query_text FROM operator_queries_v ORDER BY random() LIMIT %s",
            (n,),
        )
        return [r[0] for r in cur.fetchall() if r[0]]


def iter_voyage_emails(
    conn: psycopg.Connection,
    voyage_keys: Iterable[str],
) -> Iterable[tuple[str, list[EmailSample]]]:
    for vk in voyage_keys:
        yield vk, pick_emails_for_voyage(conn, vk)
