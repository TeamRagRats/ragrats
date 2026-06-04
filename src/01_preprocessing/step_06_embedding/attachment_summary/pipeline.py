from __future__ import annotations

# Per-email orchestrator for attachment-summary embedding:
#   1. Fetch rows from email_attach_summaries (status=ok) not yet summary-chunked
#   2. For each row: embed(summary) -> upsert chunk with source_type='attachment',
#      source_id=email_id, strategy='summary'

import logging
from datetime import datetime, timezone
from uuid import UUID

import psycopg

from log.log_chunking import log_chunking_pending, log_chunking_finished

from step_06_embedding._shared.embedder import embed_text, format_halfvec
from . import db

MAX_LENGTH = 32768
MODEL_NAME = "Qwen/Qwen3-Embedding-4B"


def _process_row(
    conn: psycopg.Connection,
    embed_model,
    tokenizer,
    device: str,
    run_id: UUID,
    row: dict,
    logger: logging.Logger,
) -> int:
    email_id = row["email_id"]
    summary = row["summary"].strip()

    started = datetime.now(timezone.utc)
    log_chunking_pending(
        conn,
        source_type="attachment",
        source_id=str(email_id),
        voyage_key=row["voyage_key"],
        started_at=started,
        run_id=run_id,
    )

    try:
        vec, n_tokens, truncated = embed_text(
            embed_model, tokenizer, summary, device, MAX_LENGTH
        )

        chunk_row = {
            "source_type": "attachment",
            "source_id":   str(email_id),
            "voyage_key":  row["voyage_key"],
            "thread_id":   str(row["thread_id"]) if row["thread_id"] else None,
            "chunk_index": 0,
            "text":        summary,
            "embedding":   format_halfvec(vec),
            "char_count":  len(summary),
            "strategy":    "summary",
            "chunker":     "naive",
            "model":       MODEL_NAME,
        }
        db.upsert_chunks(conn, [chunk_row])

        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)
        log_chunking_finished(
            conn,
            source_type="attachment",
            source_id=str(email_id),
            finished_at=finished,
            duration_ms=duration_ms,
            status="ok",
            n_chunks=1,
            char_count=len(summary),
            total_tokens=n_tokens,
            truncated=truncated,
        )
        if truncated:
            logger.warning("email %s attach summary hit max length (%d tokens)", email_id, n_tokens)
        logger.info("email %s attach summary -> 1 chunk (%d tokens%s)", email_id, n_tokens, ", truncated" if truncated else "")
        return 1

    except Exception as exc:
        conn.rollback()
        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)
        log_chunking_finished(
            conn,
            source_type="attachment",
            source_id=str(email_id),
            finished_at=finished,
            duration_ms=duration_ms,
            status="error",
            error_message=str(exc)[:500],
        )
        logger.error("email %s attach summary failed: %s", email_id, exc, exc_info=True)
        raise


def run(
    conn: psycopg.Connection,
    embed_model,
    tokenizer,
    device: str,
    run_id: UUID,
    logger: logging.Logger,
    limit: int | None,
    voyage: str | None,
) -> int:
    rows = db.get_pending(conn, voyage=voyage, limit=limit)
    logger.info("Found %d pending attach summaries", len(rows))

    total = 0
    for row in rows:
        try:
            total += _process_row(conn, embed_model, tokenizer, device, run_id, row, logger)
        except Exception:
            continue
    return total
