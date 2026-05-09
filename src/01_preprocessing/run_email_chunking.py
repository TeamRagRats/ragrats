from __future__ import annotations

# Entry point for late chunking of email threads (step_05_chunking/email_late).
# Concatenates each thread, encodes via the token-pooling vLLM server (:8004),
# mean-pools per message, and writes per-message chunks with context-aware
# embeddings into the chunks table.
#
# Run: python -m src.01_preprocessing.run_email_chunking [--limit N] [--verbose]

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

from clients.embed_client import EmbedTokensClient, wait_for_server, DEFAULT_TOKEN_BASE_URL
from core.db import connect
from log.log_run import finish_run, start_run

from step_05_chunking.email_late import pipeline

MAX_RETRIES = 10
RETRY_DELAY = 30


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


def _run_pipeline(args: argparse.Namespace, tokenizer, client, logger: logging.Logger) -> None:
    with connect() as conn:
        run_id = start_run(conn)
        status = "ok"
        try:
            logger.info("=" * 60)
            logger.info("Email Late Chunking Pipeline")
            logger.info("=" * 60)
            total = pipeline.run(conn, tokenizer, client, run_id, logger, args.limit)
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
    parser.add_argument("--token-server", default=DEFAULT_TOKEN_BASE_URL,
                        help=f"Base URL for token-pooling vLLM (default: {DEFAULT_TOKEN_BASE_URL})")
    args = parser.parse_args()

    logger = _setup_logging(verbose=args.verbose)

    logger.info("Indlæser tokenizer ...")
    tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-Embedding-4B")
    logger.info("Tokenizer klar")

    logger.info("Venter på token-pooling server (%s) ...", args.token_server)
    if not wait_for_server(args.token_server, timeout_s=120):
        logger.error("Token-pooling server svarer ikke på %s. Start den med "
                     "`docker compose -f docker/embed_token/docker-compose.yml up -d`.",
                     args.token_server)
        sys.exit(1)

    client = EmbedTokensClient(base_url=args.token_server)
    logger.info("Token-pooling client klar (model=%s)", client.model)

    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            logger.warning("Genstart %d/%d om %ds ...", attempt, MAX_RETRIES, RETRY_DELAY)
            time.sleep(RETRY_DELAY)

        try:
            t0 = time.monotonic()
            logger.info("Starter pipeline (forsøg %d/%d)", attempt, MAX_RETRIES)
            _run_pipeline(args, tokenizer, client, logger)
            logger.info("Pipeline færdig. Total wall-time: %.1fs", time.monotonic() - t0)
            return
        except Exception as exc:
            logger.error("Pipeline crashede: %s", exc, exc_info=True)
            if attempt == MAX_RETRIES:
                logger.error("Max genstarter nået — stopper.")
                sys.exit(1)


if __name__ == "__main__":
    main()
