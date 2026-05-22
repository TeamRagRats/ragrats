"""Source matching for the retrieval tests — two recall levels.

Thread recall: any chunk whose canonical thread matches the expected thread.
Emails are embedded with full thread context, so any chunk in the same thread
as the ground-truth email counts.

Email recall: strict — chunk's canonical email must equal the ground-truth
email_id. email_hit always implies thread_hit, never the reverse.

Both metrics resolve attachment chunks back to their parent email regardless
of embedding strategy (summary attachment chunks use source_id = parent
email_id; plain/late/context attachment chunks use source_id = sha256).

Shared between chunk_retrieval/run_test.py and e2e_retrieval/run_test.py.
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


def canonical_email(
    source_type: str,
    source_id: str,
    strategy: str,
    attach_email_map: dict[str, str],
) -> str | None:
    """Resolve a chunk's source_id back to its underlying email_id."""
    if source_type == "email":
        return source_id
    if strategy == "summary":
        # summary attachment chunks use source_id = email_id of the parent email
        return source_id
    # plain/late/context attachment chunks use source_id = attachment.sha256
    return attach_email_map.get(source_id)


def canonical_thread(
    source_type: str,
    source_id: str,
    strategy: str,
    email_thread_map: dict[str, str],
    attach_email_map: dict[str, str],
) -> str | None:
    """Cross-strategy thread key. Same email thread = same source, regardless of strategy."""
    email_id = canonical_email(source_type, source_id, strategy, attach_email_map)
    return email_thread_map.get(email_id) if email_id else None


def compute_thread_rank(
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


def compute_email_rank(
    chunks: list,
    expected_email_id: str | None,
    attach_email_map: dict[str, str],
) -> int | None:
    if not expected_email_id:
        return None
    for i, chunk in enumerate(chunks, 1):
        email_id = canonical_email(
            chunk.source_type, chunk.source_id, chunk.strategy, attach_email_map,
        )
        if email_id == expected_email_id:
            return i
    return None


def serialize_chunks(chunks: list) -> list[dict]:
    """Retrieved-chunk metadata + text for logging."""
    return [
        {
            "rank": i,
            "chunk_id": c.chunk_id,
            "source_id": c.source_id,
            "source_type": c.source_type,
            "strategy": c.strategy,
            "voyage_key": c.voyage_key,
            "similarity": round(float(c.similarity), 6),
            "text": c.text,
        }
        for i, c in enumerate(chunks, 1)
    ]
