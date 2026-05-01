from __future__ import annotations

# Entry point for the chunking step (step_10).
# Splits email, thread, and phase summaries into chunks and inserts them with NULL embedding.
# Run: python -m src.preprocessing.run_chunking [--limit N] [--verbose]

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _repo_root = _here.parents[1]
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_here))
    __package__ = "src.preprocessing"

import argparse
import logging
import sys
import time
from datetime import datetime, timezone

from transformers import AutoTokenizer

from core.db import connect
from log.log_run import finish_run, start_run
from log.log_chunking import log_chunking_pending, log_chunking_finished
from step_05_chunking.late.chunker import split_sentences, truncate_to_context
from step_05_chunking.late_overlap.chunker import build_overlap_chunks
from step_05_chunking.db import (
    get_pending_emails,
    get_pending_threads,
    get_pending_phases,
    upsert_chunks,
)

MAX_RETRIES = 10
RETRY_DELAY = 30


def _setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("chunking")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


def _chunk_and_upsert(
    conn,
    source_type: str,
    source_id: str,
    voyage_key: str,
    strategy: str,
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
        n = upsert_chunks(conn, source_type, source_id, voyage_key, strategy, chunks)
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


def _run_pipeline(args: argparse.Namespace, tokenizer, logger: logging.Logger) -> None:
    with connect() as conn:
        run_id = start_run(conn)
        status = "ok"
        try:
            logger.info("=" * 60)
            logger.info("Chunking Pipeline")
            logger.info("=" * 60)

            # --- Emails ---
            emails = get_pending_emails(conn)
            if args.limit is not None:
                emails = emails[:args.limit]
            logger.info(f"[chunk] {len(emails)} email(s) afventer chunking")

            email_done = 0
            for email in emails:
                email_done += _chunk_and_upsert(
                    conn,
                    source_type="email",
                    source_id=str(email["email_id"]),
                    voyage_key=email["voyage_key"],
                    strategy="late",
                    summary=email["summary"],
                    tokenizer=tokenizer,
                    run_id=run_id,
                    label=f"email {email['email_id']}",
                    logger=logger,
                )
            logger.info(f"[chunk] Emails færdige: {email_done} chunks indsat")

            # --- Threads ---
            threads = get_pending_threads(conn)
            if args.limit is not None:
                threads = threads[:args.limit]
            logger.info(f"[chunk] {len(threads)} thread(s) afventer chunking")

            thread_done = 0
            for thread in threads:
                thread_done += _chunk_and_upsert(
                    conn,
                    source_type="thread",
                    source_id=str(thread["thread_id"]),
                    voyage_key=thread["voyage_key"],
                    strategy="late",
                    summary=thread["summary"],
                    tokenizer=tokenizer,
                    run_id=run_id,
                    label=f"thread {thread['thread_id']}",
                    logger=logger,
                )
            logger.info(f"[chunk] Threads færdige: {thread_done} chunks indsat")

            # --- Phases ---
            phases_by_voyage = get_pending_phases(conn)
            voyage_keys = list(phases_by_voyage.keys())
            if args.limit is not None:
                voyage_keys = voyage_keys[:args.limit]
            logger.info(f"[chunk] {len(voyage_keys)} voyage(r) med phases afventer chunking")

            phase_done = 0
            for voyage_key in voyage_keys:
                phases = phases_by_voyage[voyage_key]
                started_at = datetime.now(timezone.utc)
                t0 = time.monotonic()
                try:
                    chunks = build_overlap_chunks(phases)
                    n = 0
                    for chunk in chunks:
                        source_id = f"{voyage_key}__{chunk['chunk_index']}"
                        log_chunking_pending(conn, "phase", source_id, voyage_key, started_at, run_id)
                        inserted = upsert_chunks(
                            conn, "phase", source_id, voyage_key, "late_overlap",
                            [chunk],
                        )
                        log_chunking_finished(
                            conn, "phase", source_id,
                            finished_at=datetime.now(timezone.utc),
                            duration_ms=int((time.monotonic() - t0) * 1000),
                            status="ok", n_chunks=inserted, char_count=chunk["char_count"],
                        )
                        n += inserted
                    phase_done += n
                    logger.debug(f"  [chunk] phases {voyage_key}: {n} chunks indsat")
                except Exception as exc:
                    log_chunking_finished(
                        conn, "phase", voyage_key,
                        finished_at=datetime.now(timezone.utc),
                        duration_ms=int((time.monotonic() - t0) * 1000),
                        status="error", error_message=f"{type(exc).__name__}: {exc}",
                    )
                    raise
            logger.info(f"[chunk] Phases færdige: {phase_done} chunks indsat")

            logger.info(f"[chunk] Total: {email_done + thread_done + phase_done} chunks indsat")

        except Exception:
            status = "failed"
            raise
        finally:
            finish_run(conn, run_id, status)


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunking Pipeline")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="Behandl kun de første N poster per type (til test)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logger = _setup_logging(verbose=args.verbose)

    logger.info("Indlæser tokenizer ...")
    tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-Embedding-4B")
    logger.info("Tokenizer klar")

    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            logger.warning(f"Genstart {attempt}/{MAX_RETRIES} om {RETRY_DELAY}s ...")
            time.sleep(RETRY_DELAY)

        try:
            t0 = time.monotonic()
            logger.info(f"Starter pipeline (forsøg {attempt}/{MAX_RETRIES})")
            _run_pipeline(args, tokenizer, logger)
            logger.info(f"Pipeline færdig. Total wall-time: {time.monotonic() - t0:.1f}s")
            return
        except Exception as exc:
            logger.error(f"Pipeline crashede: {exc}", exc_info=True)
            if attempt == MAX_RETRIES:
                logger.error("Max genstarter nået — stopper.")
                sys.exit(1)


if __name__ == "__main__":
    main()
