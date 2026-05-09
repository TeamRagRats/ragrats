from __future__ import annotations

# Per-thread orchestrator for email late chunking:
#   1. fetch pending threads
#   2. for each thread: concat -> embed_tokens -> mean-pool per message -> upsert chunks + log

import logging
from datetime import datetime, timezone
from uuid import UUID

import psycopg

from clients.embed_client import EmbedTokensClient
from log.log_chunking import log_chunking_pending, log_chunking_finished

from . import chunker, db

LATE_MAX_TOKENS = 32768  # must match docker/embed_token --max-model-len


def _process_thread(
    conn: psycopg.Connection,
    tokenizer,
    client: EmbedTokensClient,
    run_id: UUID,
    thread_id: UUID,
    logger: logging.Logger,
) -> int:
    emails = db.get_thread_emails(conn, thread_id)
    if not emails:
        return 0

    voyage_key = emails[0]["voyage_key"]
    started = datetime.now(timezone.utc)
    log_chunking_pending(
        conn,
        source_type="emails",
        source_id=str(thread_id),
        voyage_key=voyage_key,
        started_at=started,
        run_id=run_id,
    )

    try:
        full_text, char_spans = chunker.build_thread_text(emails)
        token_vectors = client.embed_tokens(full_text)
        n_tokens = len(token_vectors)
        token_spans = chunker.char_spans_to_token_spans(
            tokenizer, full_text, char_spans, n_tokens
        )

        rows: list[dict] = []
        for i, (email, span) in enumerate(zip(emails, token_spans)):
            vec = chunker.mean_pool(token_vectors, span)
            rows.append({
                "source_type": "emails",
                "source_id": str(email["email_id"]),
                "voyage_key": email["voyage_key"],
                "thread_id": str(thread_id),
                "chunk_index": i,
                "text": email["body_cleaned"],
                "embedding": chunker.format_halfvec(vec),
                "char_count": len(email["body_cleaned"]),
                "strategy": "late",
            })
        db.upsert_chunks(conn, rows)

        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)
        truncated = n_tokens >= LATE_MAX_TOKENS
        log_chunking_finished(
            conn,
            source_type="emails",
            source_id=str(thread_id),
            finished_at=finished,
            duration_ms=duration_ms,
            status="ok",
            n_chunks=len(rows),
            char_count=len(full_text),
            total_tokens=n_tokens,
            truncated=truncated,
        )
        if truncated:
            logger.warning(
                "thread %s hit max-model-len (%d tokens); embeddings of late "
                "messages may be missing context", thread_id, n_tokens,
            )
        logger.info("thread %s -> %d chunks (%d tokens%s)",
                    thread_id, len(rows), n_tokens,
                    ", truncated" if truncated else "")
        return len(rows)
    except Exception as exc:
        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)
        log_chunking_finished(
            conn,
            source_type="emails",
            source_id=str(thread_id),
            finished_at=finished,
            duration_ms=duration_ms,
            status="error",
            error_message=str(exc)[:500],
        )
        logger.error("thread %s failed: %s", thread_id, exc, exc_info=True)
        raise


def run(
    conn: psycopg.Connection,
    tokenizer,
    client: EmbedTokensClient,
    run_id: UUID,
    logger: logging.Logger,
    limit: int | None,
) -> int:
    thread_ids = db.get_pending_thread_ids(conn, limit)
    logger.info("Found %d pending threads", len(thread_ids))

    total = 0
    for thread_id in thread_ids:
        try:
            total += _process_thread(conn, tokenizer, client, run_id, thread_id, logger)
        except Exception:
            # Already logged in _process_thread; continue with the next one.
            continue
    return total
