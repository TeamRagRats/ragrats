from __future__ import annotations

# Per-thread orchestrator for email late chunking:
#   1. fetch pending threads
#   2. for each thread: concat -> local model forward pass -> mean-pool per message -> upsert + log

import logging
from datetime import datetime, timezone
from uuid import UUID

import psycopg

from log.log_chunking import log_chunking_pending, log_chunking_finished

from . import chunker, db, model as M

MAX_LENGTH = 32768


def _process_thread(
    conn: psycopg.Connection,
    embed_model,
    tokenizer,
    device: str,
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
        source_type="email",
        source_id=str(thread_id),
        voyage_key=voyage_key,
        started_at=started,
        run_id=run_id,
    )

    try:
        full_text, char_spans = chunker.build_thread_text(emails)
        token_vectors = M.get_token_embeddings(embed_model, tokenizer, full_text, device, MAX_LENGTH)
        n_tokens = len(token_vectors)
        token_spans = chunker.char_spans_to_token_spans(tokenizer, full_text, char_spans, n_tokens)

        rows: list[dict] = []
        for i, (email, span) in enumerate(zip(emails, token_spans)):
            vec = chunker.mean_pool(token_vectors, span)
            rows.append({
                "source_type": "email",
                "source_id": str(email["email_id"]),
                "voyage_key": email["voyage_key"],
                "thread_id": str(thread_id),
                "chunk_index": i,
                "text": email["body_cleaned"],
                "embedding": chunker.format_halfvec(vec),
                "char_count": len(email["body_cleaned"]),
                "strategy": "late",
                "model": "Qwen/Qwen3-Embedding-4B",
            })
        db.upsert_chunks(conn, rows)

        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)
        truncated = n_tokens >= MAX_LENGTH
        log_chunking_finished(
            conn,
            source_type="email",
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
                "thread %s hit max length (%d tokens); late messages may lack full context",
                thread_id, n_tokens,
            )
        logger.info("thread %s -> %d chunks (%d tokens%s)",
                    thread_id, len(rows), n_tokens, ", truncated" if truncated else "")
        return len(rows)

    except Exception as exc:
        conn.rollback()
        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)
        log_chunking_finished(
            conn,
            source_type="email",
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
    embed_model,
    tokenizer,
    device: str,
    run_id: UUID,
    logger: logging.Logger,
    limit: int | None,
) -> int:
    thread_ids = db.get_pending_thread_ids(conn, limit)
    logger.info("Found %d pending threads", len(thread_ids))

    total = 0
    for thread_id in thread_ids:
        try:
            total += _process_thread(
                conn, embed_model, tokenizer, device, run_id, thread_id, logger
            )
        except Exception:
            continue
    return total
