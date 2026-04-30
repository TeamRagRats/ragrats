from __future__ import annotations

# Entry point for voyage summarisation (step_09 phase 2).
# Waits for the vLLM server, then map-reduces email summaries into voyage narratives.
# Retries up to MAX_RETRIES times if the LLM server goes down mid-run.
# Run: python -m src.preprocessing.run_voyage_summaries [--voyage-key KEY] [--limit N] [--workers N] [--verbose]

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

from shared.db import connect
from shared.logging.run_logger import finish_run, start_run
from clients.llm_client import LLMClient, wait_for_server, DEFAULT_BASE_URL
import step_09_summaries.voyage.voyage_summaries as step2

MAX_RETRIES = 10
RETRY_DELAY = 30


def _setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("voyage_summaries")
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
            logger.info("Voyage Summaries")
            logger.info("=" * 60)
            step2.run(
                conn, run_id,
                limit=args.limit,
                llm=llm,
                logger=logger,
                workers=args.workers,
                voyage_key=args.voyage_key,
            )
        except Exception:
            status = "failed"
            raise
        finally:
            finish_run(conn, run_id, status)


def main() -> None:
    parser = argparse.ArgumentParser(description="Voyage Summaries Pipeline")
    parser.add_argument("--voyage-key", type=str, default=None, metavar="KEY",
                        help="Kør kun for én specifik voyage (springer get_pending_voyages over)")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="Behandl kun de første N voyages (til test, ignoreret hvis --voyage-key er sat)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Antal parallelle workers (default: 4)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logger = _setup_logging(verbose=args.verbose)

    base_url = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL)
    logger.info(f"Venter på LLM server: {base_url} ...")
    if not wait_for_server(base_url, timeout_s=60):
        logger.error(f"LLM server ikke tilgængelig: {base_url}")
        sys.exit(1)

    llm = LLMClient(base_url=base_url)
    logger.info(f"Model: {llm.model} | Workers: {args.workers}")

    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            logger.warning(f"Genstart {attempt}/{MAX_RETRIES} om {RETRY_DELAY}s ...")
            time.sleep(RETRY_DELAY)
            if not wait_for_server(base_url, timeout_s=60):
                logger.error("LLM server nede ved genstart — afventer ...")
                continue

        try:
            t0 = time.monotonic()
            logger.info(f"Starter pipeline (forsøg {attempt}/{MAX_RETRIES})")
            _run_pipeline(args, llm, logger)
            logger.info(f"Pipeline færdig. Total wall-time: {time.monotonic() - t0:.1f}s")
            return
        except Exception as exc:
            logger.error(f"Pipeline crashede: {exc}", exc_info=True)
            if attempt == MAX_RETRIES:
                logger.error("Max genstarter nået — stopper.")
                sys.exit(1)


if __name__ == "__main__":
    main()
