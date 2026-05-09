from __future__ import annotations

# Shared helper for late-strategy sources (email, fixture, llm_structured):
# split into sentences, truncate to context, upsert + log.

import logging
import time
from datetime import datetime, timezone

from log.log_chunking import log_chunking_pending, log_chunking_finished

from .db import upsert_chunks
from .late.chunker import split_sentences, truncate_to_context


def chunk_late_and_upsert(
    conn,
    source_type: str,
    source_id: str,
    voyage_key: str,
    summary: str,
    tokenizer,
    run_id,
    label: str,
    logger: logging.Logger,
) -> int:
    started_at = datetime.now(timezone.utc)
    t0 = time.monotonic()
    log_chunking_pending(conn, source_type, source_id, voyage_key, started_at, run_id)
    try:
        sentences = split_sentences(summary)
        sentences = truncate_to_context(sentences, tokenizer)
        chunks = [
            {"chunk_index": i, "text": s, "char_count": len(s)}
            for i, s in enumerate(sentences)
        ]
        n = upsert_chunks(conn, source_type, source_id, voyage_key, "late", chunks)
        total_chars = sum(len(s) for s in sentences)
        log_chunking_finished(
            conn, source_type, source_id,
            finished_at=datetime.now(timezone.utc),
            duration_ms=int((time.monotonic() - t0) * 1000),
            status="ok", n_chunks=n, char_count=total_chars,
        )
        logger.debug(f"  [chunk] {label}: {n} chunks indsat")
        return n
    except Exception as exc:
        log_chunking_finished(
            conn, source_type, source_id,
            finished_at=datetime.now(timezone.utc),
            duration_ms=int((time.monotonic() - t0) * 1000),
            status="error", error_message=f"{type(exc).__name__}: {exc}",
        )
        raise
