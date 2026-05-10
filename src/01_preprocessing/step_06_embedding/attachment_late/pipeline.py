from __future__ import annotations

# Per-attachment orchestrator for late chunking:
#   1. fetch pending sha256s
#   2. for each: build input (email_summary + structured_md) → forward pass
#      → mean-pool token embeddings per chunk boundary → upsert + log

import logging
from datetime import datetime, timezone
from uuid import UUID

import psycopg

from log.log_chunking import log_chunking_pending, log_chunking_finished
from step_05_chunking.attachments.chunker import chunk_structured_md
from step_05_chunking.email_late.chunker import (
    char_spans_to_token_spans,
    format_halfvec,
    mean_pool,
)
from step_06_embedding.email_late import model as M

from . import db

MAX_LENGTH = 32768
SEPARATOR = "\n\n---\n\n"
MODEL_NAME = "Qwen/Qwen3-Embedding-4B"


def _build_input_text(email_summary: str | None, structured_md: str) -> tuple[str, int]:
    """Prepend email summary when available.

    Returns (full_text, doc_offset) where doc_offset is the char position
    at which structured_md begins inside full_text. Token spans are pooled
    only over the document portion (email summary influences via attention).
    """
    if email_summary and email_summary.strip():
        prefix = email_summary.strip() + SEPARATOR
        return prefix + structured_md, len(prefix)
    return structured_md, 0


def _get_chunk_char_spans(
    structured_md: str,
    chunks: list,
) -> list[tuple[int, int]]:
    """Locate each chunk's text within structured_md via sequential search.

    Returns (start, end) char offsets relative to structured_md.
    Falls back to (cursor, cursor) if a chunk text is not found.
    """
    spans: list[tuple[int, int]] = []
    cursor = 0
    for chunk in chunks:
        pos = structured_md.find(chunk.text, cursor)
        if pos == -1:
            # Stripped text may not match exactly — use cursor as best guess
            spans.append((cursor, cursor + chunk.char_count))
        else:
            spans.append((pos, pos + len(chunk.text)))
            cursor = pos + len(chunk.text)
    return spans


def _process_attachment(
    conn: psycopg.Connection,
    embed_model,
    tokenizer,
    device: str,
    run_id: UUID,
    sha256: str,
    logger: logging.Logger,
) -> int:
    data = db.get_attachment_data(conn, sha256)
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
        full_text, doc_offset = _build_input_text(data["email_summary"], structured_md)
        token_vectors = M.get_token_embeddings(embed_model, tokenizer, full_text, device, MAX_LENGTH)
        n_tokens = len(token_vectors)

        raw_spans = _get_chunk_char_spans(structured_md, chunks)
        adjusted_spans = [(doc_offset + s, doc_offset + e) for s, e in raw_spans]
        token_spans = char_spans_to_token_spans(tokenizer, full_text, adjusted_spans, n_tokens)

        rows: list[dict] = []
        for chunk, span in zip(chunks, token_spans):
            vec = mean_pool(token_vectors, span)
            rows.append({
                "source_type": "attachment",
                "source_id":   sha256,
                "voyage_key":  voyage_key,
                "thread_id":   str(thread_id) if thread_id else None,
                "chunk_index": chunk.chunk_index,
                "text":        chunk.text,
                "embedding":   format_halfvec(vec),
                "char_count":  chunk.char_count,
                "strategy":    "late",
                "model":       MODEL_NAME,
            })

        db.upsert_chunks(conn, rows)

        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)
        truncated = n_tokens >= MAX_LENGTH
        log_chunking_finished(
            conn,
            source_type="attachment",
            source_id=sha256,
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
                "sha256 %s hit max length (%d tokens); later chunks may lack full context",
                sha256, n_tokens,
            )
        logger.info("sha256 %.12s → %d chunks (%d tokens%s)",
                    sha256, len(rows), n_tokens, ", truncated" if truncated else "")
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
    sha256s = db.get_pending_sha256s(conn, voyage=voyage, limit=limit)
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
