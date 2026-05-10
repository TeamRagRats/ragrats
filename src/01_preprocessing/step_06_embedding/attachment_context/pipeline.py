from __future__ import annotations

# Per-attachment orchestrator for context chunking:
#   For each chunk: embed(email_summary + chunk.text) → one vector per chunk.
#   No full-doc forward pass — each chunk is embedded independently with the
#   email summary prepended for context (last-token pooling, L2-normalised).

import logging
from datetime import datetime, timezone
from uuid import UUID

import psycopg

from log.log_chunking import log_chunking_pending, log_chunking_finished
from step_05_chunking.attachments.chunker import chunk_structured_md
from step_06_embedding.email_context.embedder import embed_text, format_halfvec
from step_06_embedding.attachment_context.db import (
    get_pending_sha256s,
    get_attachment_data,
    upsert_chunks,
)

MAX_LENGTH = 32768
MODEL_NAME = "Qwen/Qwen3-Embedding-4B"


def _build_embed_input(email_summary: str | None, chunk_text: str) -> str:
    """Prepend email summary when available."""
    if email_summary and email_summary.strip():
        return f"{email_summary.strip()}\n\n{chunk_text}"
    return chunk_text


def _process_attachment(
    conn: psycopg.Connection,
    embed_model,
    tokenizer,
    device: str,
    run_id: UUID,
    sha256: str,
    logger: logging.Logger,
) -> int:
    data = get_attachment_data(conn, sha256)
    if data is None:
        logger.warning("sha256 %s not found — skipping", sha256)
        return 0

    structured_md: str = data["structured_md"]
    chunks = chunk_structured_md(structured_md)
    if not chunks:
        logger.warning("sha256 %s produced no chunks — skipping", sha256)
        return 0

    voyage_key: str = data["voyage_key"] or ""
    thread_id = data["thread_id"]
    email_summary: str | None = data["email_summary"]
    started = datetime.now(timezone.utc)

    log_chunking_pending(
        conn,
        source_type="attachment",
        source_id=sha256,
        voyage_key=voyage_key,
        started_at=started,
        run_id=run_id,
    )

    try:
        rows: list[dict] = []
        total_tokens = 0
        any_truncated = False

        for chunk in chunks:
            embed_input = _build_embed_input(email_summary, chunk.text)
            vec, n_tokens, truncated = embed_text(
                embed_model, tokenizer, embed_input, device, MAX_LENGTH
            )
            total_tokens += n_tokens
            if truncated:
                any_truncated = True
                logger.warning(
                    "sha256 %.12s chunk %d hit max length (%d tokens)",
                    sha256, chunk.chunk_index, n_tokens,
                )
            rows.append({
                "source_type": "attachment",
                "source_id":   sha256,
                "voyage_key":  voyage_key,
                "thread_id":   str(thread_id) if thread_id else None,
                "chunk_index": chunk.chunk_index,
                "text":        chunk.text,
                "embedding":   format_halfvec(vec),
                "char_count":  chunk.char_count,
                "strategy":    "context",
                "model":       MODEL_NAME,
            })

        upsert_chunks(conn, rows)

        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)
        log_chunking_finished(
            conn,
            source_type="attachment",
            source_id=sha256,
            finished_at=finished,
            duration_ms=duration_ms,
            status="ok",
            n_chunks=len(rows),
            char_count=len(structured_md),
            total_tokens=total_tokens,
            truncated=any_truncated,
        )
        logger.info("sha256 %.12s → %d chunks (%d tokens total%s)",
                    sha256, len(rows), total_tokens, ", truncated" if any_truncated else "")
        return len(rows)

    except Exception as exc:
        conn.rollback()
        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)
        log_chunking_finished(
            conn,
            source_type="attachment",
            source_id=sha256,
            finished_at=finished,
            duration_ms=duration_ms,
            status="error",
            error_message=str(exc)[:500],
        )
        logger.error("sha256 %s failed: %s", sha256, exc, exc_info=True)
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
    sha256s = get_pending_sha256s(conn, voyage=voyage, limit=limit)
    logger.info("Found %d pending attachments", len(sha256s))

    total = 0
    for sha256 in sha256s:
        try:
            total += _process_attachment(
                conn, embed_model, tokenizer, device, run_id, sha256, logger
            )
        except Exception:
            continue
    return total
