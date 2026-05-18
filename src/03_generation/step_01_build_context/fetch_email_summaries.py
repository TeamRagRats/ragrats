from __future__ import annotations

import psycopg

from step_02_chunk_retrieval.retrieve_vector import RetrievedChunk


def fetch_email_summaries(
    conn: psycopg.Connection,
    chunks: list[RetrievedChunk],
) -> tuple[dict[str, str], dict[str, str]]:
    """Resolve each chunk to the email_thread_summaries row of its parent email.

    Returns (chunk_email_id, email_summary):
      - chunk_email_id: chunk_id -> email_id (only chunks resolvable to an email).
        Email chunks resolve directly via source_id; attachment chunks resolve via
        attachments.sha256 -> attachments.email_id.
      - email_summary: email_id -> thread summary text (status='ok' rows only).
    """
    if not chunks:
        return {}, {}

    chunk_email_id: dict[str, str] = {}
    attachment_chunks: list[RetrievedChunk] = []

    for c in chunks:
        if c.source_type == "email":
            chunk_email_id[c.chunk_id] = c.source_id
        elif c.source_type == "attachment":
            attachment_chunks.append(c)

    if attachment_chunks:
        shas = list({c.source_id for c in attachment_chunks})
        rows = conn.execute(
            """
            SELECT sha256, email_id::text
            FROM attachments
            WHERE sha256 = ANY(%s) AND email_id IS NOT NULL
            """,
            [shas],
        ).fetchall()
        sha_to_email = {sha: email_id for sha, email_id in rows}
        for c in attachment_chunks:
            email_id = sha_to_email.get(c.source_id)
            if email_id is not None:
                chunk_email_id[c.chunk_id] = email_id

    email_ids = list(set(chunk_email_id.values()))
    if not email_ids:
        return chunk_email_id, {}

    rows = conn.execute(
        """
        SELECT email_id::text, summary
        FROM email_thread_summaries
        WHERE email_id = ANY(%s::uuid[])
          AND status = 'ok'
          AND summary <> ''
        """,
        [email_ids],
    ).fetchall()
    email_summary = {email_id: summary for email_id, summary in rows}

    return chunk_email_id, email_summary
