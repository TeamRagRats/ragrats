from __future__ import annotations

# Entry point for email + attachment summarisation (step_09 phase 1).
# Waits for the vLLM server, then summarises each unsummarised email and its attachments.
# Retries up to MAX_RETRIES times if the LLM server goes down mid-run.
# Run: python -m src.preprocessing.run_email_attach_summaries [--limit N] [--workers N] [--verbose]

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
import os
import sys
import time

from core.db import connect
from log.log_run import finish_run, start_run
from clients.llm_client import LLMClient, wait_for_server, DEFAULT_BASE_URL
import step_04_summaries.email_attach.email_summaries as step1

MAX_RETRIES = 10
RETRY_DELAY = 30


def _setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("email_attach_summaries")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


def _run_pipeline(args: argparse.Namespace, llm: LLMClient, logger: logging.Logger) -> None:
    with connect() as conn:
        run_id = start_run(conn)
        status = "ok"
        try:
            logger.info("=" * 60)
            logger.info("Email + Attachment Summaries")
            logger.info("=" * 60)
            step1.run(conn, run_id, limit=args.limit, llm=llm, logger=logger, workers=args.workers)
        except Exception:
            status = "failed"
            raise
        finally:
            finish_run(conn, run_id, status)


def main() -> None:
    parser = argparse.ArgumentParser(description="Email + Attachment Summaries Pipeline")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="Process only the first N emails (for testing)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Number of parallel workers (default: 4)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logger = _setup_logging(verbose=args.verbose)

    base_url = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL)
    logger.info(f"Waiting for LLM server: {base_url} ...")
    if not wait_for_server(base_url, timeout_s=60):
        logger.error(f"LLM server not available: {base_url}")
        sys.exit(1)

    llm = LLMClient(base_url=base_url)
    logger.info(f"Model: {llm.model} | Workers: {args.workers}")

    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            logger.warning(f"Restart {attempt}/{MAX_RETRIES} in {RETRY_DELAY}s ...")
            time.sleep(RETRY_DELAY)
            if not wait_for_server(base_url, timeout_s=60):
                logger.error("LLM server down at restart — waiting ...")
                continue

        try:
            t0 = time.monotonic()
            logger.info(f"Starting pipeline (attempt {attempt}/{MAX_RETRIES})")
            _run_pipeline(args, llm, logger)
            logger.info(f"Pipeline finished. Total wall-time: {time.monotonic() - t0:.1f}s")
            return
        except Exception as exc:
            logger.error(f"Pipeline crashed: {exc}", exc_info=True)
            if attempt == MAX_RETRIES:
                logger.error("Max restarts reached — stopping.")
                sys.exit(1)


if __name__ == "__main__":
    main()
