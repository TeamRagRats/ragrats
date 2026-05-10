from __future__ import annotations

# Entry point for late embedding of attachment documents (step_06_embedding/attachment_late).
# Loads Qwen3-Embedding-4B locally, prepends email summary to each structured_md,
# encodes the combined text in full to capture cross-section attention, mean-pools
# per chunk boundary (from step_05_chunking/attachments/chunker.py), and writes
# context-aware embeddings to the chunks table (source_type='attachment', strategy='late').
#
# Run: python run_embedding_attachment_late.py [--limit N] [--voyage KEY] [--verbose]

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
from step_06_embedding.email_late import model as M
from step_06_embedding.attachment_late import pipeline

MAX_RETRIES = 10
RETRY_DELAY = 30
MODEL_NAME = "Qwen/Qwen3-Embedding-4B"


def _setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("attachment_late_chunking")
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
            logger.info("Attachment Late Chunking Pipeline")
            logger.info("=" * 60)
            total = pipeline.run(
                conn, embed_model, tokenizer, device, run_id, logger,
                limit=args.limit, voyage=args.voyage,
            )
            logger.info("[attachment_late] %d chunks inserted", total)
        except Exception:
            status = "failed"
            raise
        finally:
            finish_run(conn, run_id, status)


def main() -> None:
    parser = argparse.ArgumentParser(description="Attachment Late Chunking Pipeline")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="Process only the first N attachments (for testing)")
    parser.add_argument("--voyage", default=None, metavar="KEY",
                        help="Filter by voyage_key")
    parser.add_argument("--sha256", default=None, metavar="HASH",
                        help="Process a single attachment by sha256 (overrides --limit/--voyage)")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--device", default=None,
                        help="Torch device (default: cuda if available, else cpu)")
    args = parser.parse_args()

    logger = _setup_logging(verbose=args.verbose)

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Device: %s", device)

    logger.info("Loading tokenizer and model (%s) ...", MODEL_NAME)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    embed_model = M.load_model(device=device)
    logger.info("Model ready")

    # --sha256 shortcut: process exactly one attachment
    if args.sha256:
        with connect() as conn:
            run_id = start_run(conn)
            try:
                from step_06_embedding.attachment_late.pipeline import _process_attachment
                n = _process_attachment(conn, embed_model, tokenizer, device, run_id, args.sha256, logger)
                logger.info("Done: %d chunks", n)
            finally:
                finish_run(conn, run_id, "ok")
        return

    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            logger.warning("Retry %d/%d in %ds ...", attempt, MAX_RETRIES, RETRY_DELAY)
            time.sleep(RETRY_DELAY)

        try:
            t0 = time.monotonic()
            logger.info("Starting pipeline (attempt %d/%d)", attempt, MAX_RETRIES)
            _run_pipeline(args, embed_model, tokenizer, device, logger)
            logger.info("Pipeline done. Wall-time: %.1fs", time.monotonic() - t0)
            return
        except Exception as exc:
            logger.error("Pipeline crashed: %s", exc, exc_info=True)
            if attempt == MAX_RETRIES:
                logger.error("Max retries reached — stopping.")
                sys.exit(1)


if __name__ == "__main__":
    main()
