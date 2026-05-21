"""Source-level (thread-level for emails) matching for the chunk retrieval test.

Chunk-level recall is retired; correctness is measured at the source level:
emails match at thread level (any chunk in the expected email's thread counts),
attachments match on the parent email's thread regardless of embedding strategy.
"""
from __future__ import annotations


def load_email_thread_map(conn) -> dict[str, str]:
    """email_id (text) -> thread_id (text). Lets emails match at thread level."""
    rows = conn.execute("SELECT email_id::text, thread_id::text FROM emails").fetchall()
    return {email_id: thread_id for email_id, thread_id in rows}


def load_attachment_email_map(conn) -> dict[str, str]:
    """attachment.sha256 -> email_id (text). Resolves attachment chunks to their parent email."""
    rows = conn.execute(
        "SELECT sha256, email_id::text FROM attachments WHERE sha256 IS NOT NULL"
    ).fetchall()
    return {sha: eid for sha, eid in rows}


def canonical_thread(
    source_type: str,
    source_id: str,
    strategy: str,
    email_thread_map: dict[str, str],
    attach_email_map: dict[str, str],
) -> str | None:
    """Cross-strategy thread key. Same email thread = same source, regardless of strategy."""
    if source_type == "email":
        return email_thread_map.get(source_id)
    if strategy == "summary":
        # summary attachment chunks use source_id = email_id of the parent email
        return email_thread_map.get(source_id)
    # plain/late/context attachment chunks use source_id = attachment.sha256
    email_id = attach_email_map.get(source_id)
    return email_thread_map.get(email_id) if email_id else None


def compute_source_rank(
    chunks: list,
    expected_thread: str | None,
    email_thread_map: dict[str, str],
    attach_email_map: dict[str, str],
) -> int | None:
    if not expected_thread:
        return None
    for i, chunk in enumerate(chunks, 1):
        thread = canonical_thread(
            chunk.source_type, chunk.source_id, chunk.strategy,
            email_thread_map, attach_email_map,
        )
        if thread == expected_thread:
            return i
    return None


def serialize_chunks(chunks: list) -> list[dict]:
    """Retrieved-chunk metadata for logging (no text; look up by chunk_id)."""
    return [
        {
            "rank": i,
            "chunk_id": c.chunk_id,
            "source_id": c.source_id,
            "source_type": c.source_type,
            "strategy": c.strategy,
            "voyage_key": c.voyage_key,
            "similarity": round(float(c.similarity), 6),
        }
        for i, c in enumerate(chunks, 1)
    ]
