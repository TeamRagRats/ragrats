from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import psycopg


_MIN_BODY_CHARS = 100
_MIN_STRUCTURED_CHARS = 50


@dataclass
class EmailSample:
    email_id: UUID
    thread_id: UUID
    voyage_key: str
    body_cleaned: str
    structured_md: str  # one randomly picked attachment's structured_md


def list_voyage_keys(conn: psycopg.Connection, limit: int | None = None) -> list[str]:
    sql = "SELECT voyage_key FROM fixtures ORDER BY voyage_key"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    with conn.cursor() as cur:
        cur.execute(sql)  # type: ignore[arg-type]
        return [r[0] for r in cur.fetchall()]


def get_vessel_name(conn: psycopg.Connection, voyage_key: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT vessel_name FROM fixtures WHERE voyage_key = %s",
            (voyage_key,),
        )
        row = cur.fetchone()
    return row[0] if row and row[0] else None


def pick_emails_with_attachment(
    conn: psycopg.Connection,
    voyage_key: str,
    limit: int,
) -> list[EmailSample]:
    """Pick up to `limit` emails for the voyage that:
       - have has_attachment = true
       - have a non-trivial body_cleaned
       - have at least one attachment whose llm_structured.structured_md is non-empty

    For each chosen email, exactly one matching attachment is picked at random
    and its structured_md returned alongside the email body. The returned list
    is in random order.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH email_attach AS (
                SELECT
                    e.email_id,
                    e.thread_id,
                    e.voyage_key,
                    e.body_cleaned,
                    ls.structured_md,
                    ROW_NUMBER() OVER (
                        PARTITION BY e.email_id ORDER BY random()
                    ) AS rn_attach
                FROM emails e
                JOIN attachments    a  ON a.email_id = e.email_id
                JOIN llm_structured ls ON ls.sha256  = a.sha256
                WHERE e.voyage_key      = %s
                  AND e.has_attachment  = true
                  AND e.body_cleaned    IS NOT NULL
                  AND length(e.body_cleaned)   > %s
                  AND ls.structured_md  IS NOT NULL
                  AND length(ls.structured_md) > %s
            )
            SELECT email_id, thread_id, voyage_key, body_cleaned, structured_md
            FROM email_attach
            WHERE rn_attach = 1
            ORDER BY random()
            LIMIT %s
            """,
            (voyage_key, _MIN_BODY_CHARS, _MIN_STRUCTURED_CHARS, limit),
        )
        rows = cur.fetchall()

    return [
        EmailSample(
            email_id=email_id,
            thread_id=thread_id,
            voyage_key=vk,
            body_cleaned=body_cleaned,
            structured_md=structured_md,
        )
        for (email_id, thread_id, vk, body_cleaned, structured_md) in rows
    ]


def sample_operator_queries(conn: psycopg.Connection, n: int = 8) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT query_text FROM operator_queries_v ORDER BY random() LIMIT %s",
            (n,),
        )
        return [r[0] for r in cur.fetchall() if r[0]]
