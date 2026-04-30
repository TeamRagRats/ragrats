from __future__ import annotations

# Entry point for the chunking step (step_10).
# Splits voyage and email summaries into paragraphs and inserts chunks with NULL embedding.
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

from transformers import AutoTokenizer

from core.db import connect
from core.logging.ingest_lifecycle import finish_run, start_run
from step_10_chunking.chunker import split_paragraphs, truncate_to_context
from step_10_chunking.db import get_pending_voyages, get_voyage_summary, get_pending_emails, upsert_chunks

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


def _run_pipeline(args: argparse.Namespace, tokenizer, logger: logging.Logger) -> None:
    with connect() as conn:
        run_id = start_run(conn)
        status = "ok"
        try:
            logger.info("=" * 60)
            logger.info("Chunking Pipeline")
            logger.info("=" * 60)

            voyage_keys = get_pending_voyages(conn)
            if args.limit is not None:
                voyage_keys = voyage_keys[:args.limit]
            logger.info(f"[chunk] {len(voyage_keys)} voyage(r) afventer chunking")

            voyage_done = 0
            for voyage_key in voyage_keys:
                summary = get_voyage_summary(conn, voyage_key)
                if not summary:
                    continue
                paragraphs = split_paragraphs(summary)
                paragraphs = truncate_to_context(paragraphs, tokenizer)
                chunks = [
                    {"chunk_index": i, "text": p, "char_count": len(p)}
                    for i, p in enumerate(paragraphs)
                ]
                n = upsert_chunks(conn, "voyage", voyage_key, voyage_key, chunks)
                voyage_done += n
                logger.debug(f"  [chunk] {voyage_key}: {n} chunks indsat")

            logger.info(f"[chunk] Voyager færdige: {voyage_done} chunks indsat")

            emails = get_pending_emails(conn)
            if args.limit is not None:
                emails = emails[:args.limit]
            logger.info(f"[chunk] {len(emails)} email(s) afventer chunking")

            email_done = 0
            for email in emails:
                summary = email["summary"]
                if not summary:
                    continue
                paragraphs = split_paragraphs(summary)
                paragraphs = truncate_to_context(paragraphs, tokenizer)
                chunks = [
                    {"chunk_index": i, "text": p, "char_count": len(p)}
                    for i, p in enumerate(paragraphs)
                ]
                n = upsert_chunks(conn, "email", str(email["email_id"]), email["voyage_key"], chunks)
                email_done += n
                logger.debug(f"  [chunk] email {email['email_id']}: {n} chunks indsat")

            logger.info(f"[chunk] Emails færdige: {email_done} chunks indsat")
            logger.info(f"[chunk] Total: {voyage_done + email_done} chunks indsat")

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
