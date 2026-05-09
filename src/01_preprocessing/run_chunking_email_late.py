from __future__ import annotations

# Entry point for late chunking of email threads (step_05_chunking/email_late).
# Loads Qwen3-Embedding-4B locally, encodes each thread in full to capture
# cross-message attention, mean-pools per message, and writes context-aware
# embeddings directly into the chunks table (strategy='late').
#
# Run: python -m src.01_preprocessing.run_chunking_email_late [--limit N] [--verbose]

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

import torch
from transformers import AutoTokenizer

from core.db import connect
from log.log_run import finish_run, start_run

from step_05_chunking.email_late import model as M, pipeline

MAX_RETRIES = 10
RETRY_DELAY = 30
MODEL_NAME = "Qwen/Qwen3-Embedding-4B"


def _setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("email_chunking")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


def _run_pipeline(args, embed_model, tokenizer, device, logger) -> None:
    with connect() as conn:
        run_id = start_run(conn)
        status = "ok"
        try:
            logger.info("=" * 60)
            logger.info("Email Late Chunking Pipeline")
            logger.info("=" * 60)
            total = pipeline.run(conn, embed_model, tokenizer, device, run_id, logger, args.limit)
            logger.info("[email_late] %d chunks indsat", total)
        except Exception:
            status = "failed"
            raise
        finally:
            finish_run(conn, run_id, status)


def main() -> None:
    parser = argparse.ArgumentParser(description="Email Late Chunking Pipeline")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="Behandl kun de første N threads (til test)")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--device", default=None,
                        help="Torch device (default: cuda if available, else cpu)")
    args = parser.parse_args()

    logger = _setup_logging(verbose=args.verbose)

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Device: %s", device)

    logger.info("Indlæser tokenizer og model (%s) ...", MODEL_NAME)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    embed_model = M.load_model(device=device)
    logger.info("Model klar")

    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            logger.warning("Genstart %d/%d om %ds ...", attempt, MAX_RETRIES, RETRY_DELAY)
            time.sleep(RETRY_DELAY)

        try:
            t0 = time.monotonic()
            logger.info("Starter pipeline (forsøg %d/%d)", attempt, MAX_RETRIES)
            _run_pipeline(args, embed_model, tokenizer, device, logger)
            logger.info("Pipeline færdig. Total wall-time: %.1fs", time.monotonic() - t0)
            return
        except Exception as exc:
            logger.error("Pipeline crashede: %s", exc, exc_info=True)
            if attempt == MAX_RETRIES:
                logger.error("Max genstarter nået — stopper.")
                sys.exit(1)


if __name__ == "__main__":
    main()
