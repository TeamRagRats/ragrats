from __future__ import annotations

# Per-email orchestrator for plain chunking:
#   1. fetch emails with body_cleaned not yet plain-chunked
#   2. for each email: split body_cleaned into fixed windows (shared
#      general_chunker), embed each chunk -> upsert chunk rows + log
#   Short emails (<= TARGET_CHARS) yield a single chunk == the whole body.

import logging
from datetime import datetime, timezone
from uuid import UUID

import psycopg

from log.log_chunking import log_chunking_pending, log_chunking_finished

from step_05_chunking.emails.chunker import chunk_email_body
from step_06_embedding.email_context import embedder

from . import db

MAX_LENGTH = 32768
MODEL_NAME = "Qwen/Qwen3-Embedding-4B"


def _process_email(
    conn: psycopg.Connection,
    embed_model,
    tokenizer,
    device: str,
    run_id: UUID,
    email: dict,
    logger: logging.Logger,
) -> int:
    email_id = email["email_id"]
    body = email["body_cleaned"]
    chunks = chunk_email_body(body)
    if not chunks:
        logger.warning("email %s produced no chunks — skipping", email_id)
        return 0

    started = datetime.now(timezone.utc)
    log_chunking_pending(
        conn,
        source_type="email",
        source_id=str(email_id),
        voyage_key=email["voyage_key"],
        started_at=started,
        run_id=run_id,
    )

    try:
        rows: list[dict] = []
        total_tokens = 0
        any_truncated = False

        for chunk in chunks:
            vec, n_tokens, truncated = embedder.embed_text(
                embed_model, tokenizer, chunk.text, device, MAX_LENGTH
            )
            total_tokens += n_tokens
            if truncated:
                any_truncated = True
                logger.warning(
                    "email %s chunk %d hit max length (%d tokens)",
                    email_id, chunk.chunk_index, n_tokens,
                )
            rows.append({
                "source_type": "email",
                "source_id": str(email_id),
                "voyage_key": email["voyage_key"],
                "thread_id": str(email["thread_id"]) if email["thread_id"] else None,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "embedding": embedder.format_halfvec(vec),
                "char_count": chunk.char_count,
                "strategy": "plain",
                "model": MODEL_NAME,
            })

        db.upsert_chunks(conn, rows)

        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)
        log_chunking_finished(
            conn,
            source_type="email",
            source_id=str(email_id),
            finished_at=finished,
            duration_ms=duration_ms,
            status="ok",
            n_chunks=len(rows),
            char_count=len(body),
            total_tokens=total_tokens,
            truncated=any_truncated,
        )
        logger.info(
            "email %s -> %d chunks (%d tokens%s)",
            email_id, len(rows), total_tokens, ", truncated" if any_truncated else "",
        )
        return len(rows)

    except Exception as exc:
        conn.rollback()
        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)
        log_chunking_finished(
            conn,
            source_type="email",
            source_id=str(email_id),
            finished_at=finished,
            duration_ms=duration_ms,
            status="error",
            error_message=str(exc)[:500],
        )
        logger.error("email %s failed: %s", email_id, exc, exc_info=True)
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
    emails = db.get_pending_emails(conn, limit)
    logger.info("Found %d pending emails", len(emails))

    total = 0
    for email in emails:
        try:
            total += _process_email(
                conn, embed_model, tokenizer, device, run_id, email, logger
            )
        except Exception:
            continue
    return total
