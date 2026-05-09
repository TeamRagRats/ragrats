from __future__ import annotations

# Entry point for the chunking step (step_05).
# Orchestrates per-source-type chunkers; each source lives in
# step_05_chunking/sources/. Run: python -m src.01_preprocessing.run_chunking [--limit N] [--verbose]

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _repo_root = _here.parents[1]
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_here))
    __package__ = "src.01_preprocessing"

import argparse
import logging
import sys
import time

from transformers import AutoTokenizer

from core.db import connect
from log.log_run import finish_run, start_run

from step_05_chunking.sources import (
    email_summaries,
    fixture_summaries,
    phase,
    llm_structured,
)

MAX_RETRIES = 10
RETRY_DELAY = 30

SOURCES = [
    ("emails",          email_summaries.run),
    ("fixtures",        fixture_summaries.run),
    ("phases",          phase.run),
    ("llm_structured",  llm_structured.run),
]


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

            total = 0
            for label, source_run in SOURCES:
                logger.info(f"--- {label} ---")
                total += source_run(conn, tokenizer, run_id, logger, args.limit)

            logger.info(f"[chunk] Total: {total} chunks indsat")
        except Exception:
            status = "failed"
            raise
        finally:
            finish_run(conn, run_id, status)


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunking Pipeline")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="Behandl kun de første N poster per source-type (til test)")
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
