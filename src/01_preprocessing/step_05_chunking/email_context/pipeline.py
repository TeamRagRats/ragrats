from __future__ import annotations

# Per-email orchestrator for context chunking:
#   1. fetch emails with an OK prior-thread summary not yet context-chunked
#   2. for each email: embed (summary + body) -> upsert chunk row + log

import logging
from datetime import datetime, timezone
from uuid import UUID

import psycopg

from log.log_chunking import log_chunking_pending, log_chunking_finished

from . import db, embedder

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
    summary = (email["summary"] or "").strip()
    embed_input = f"{summary}\n\n{body}"

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
        vec, n_tokens, truncated = embedder.embed_text(
            embed_model, tokenizer, embed_input, device, MAX_LENGTH
        )

        row = {
            "source_type": "email",
            "source_id": str(email_id),
            "voyage_key": email["voyage_key"],
            "thread_id": str(email["thread_id"]) if email["thread_id"] else None,
            "chunk_index": 0,
            "text": body,
            "embedding": embedder.format_halfvec(vec),
            "char_count": len(body),
            "strategy": "context",
            "model": MODEL_NAME,
        }
        db.upsert_chunks(conn, [row])

        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)
        log_chunking_finished(
            conn,
            source_type="email",
            source_id=str(email_id),
            finished_at=finished,
            duration_ms=duration_ms,
            status="ok",
            n_chunks=1,
            char_count=len(embed_input),
            total_tokens=n_tokens,
            truncated=truncated,
        )
        if truncated:
            logger.warning(
                "email %s hit max length (%d tokens); summary+body truncated",
                email_id, n_tokens,
            )
        logger.info(
            "email %s -> 1 chunk (%d tokens%s)",
            email_id, n_tokens, ", truncated" if truncated else "",
        )
        return 1

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
