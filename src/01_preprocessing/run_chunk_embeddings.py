from __future__ import annotations

# Entry point for chunk embedding (step_11 embed stage).
# Waits for the embed server, then generates embeddings for each chunk with NULL embedding.
# Retries up to MAX_RETRIES times if the embed server goes down mid-run.
# Run: python -m src.preprocessing.run_chunk_embeddings [--limit N] [--batch-size N] [--verbose]

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
from core.logging.ingest_lifecycle import finish_run, start_run
from clients.embed_client import EmbedClient, wait_for_server, DEFAULT_BASE_URL
import step_11_embedding.chunk_embeddings as step_embed

MAX_RETRIES = 10
RETRY_DELAY = 30


def _setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("chunk_embeddings")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


def _run_pipeline(args: argparse.Namespace, client: EmbedClient, logger: logging.Logger) -> None:
    with connect() as conn:
        run_id = start_run(conn)
        status = "ok"
        try:
            logger.info("=" * 60)
            logger.info("Chunk Embeddings")
            logger.info("=" * 60)
            step_embed.run(conn, run_id, limit=args.limit, client=client, logger=logger, batch_size=args.batch_size)
        except Exception:
            status = "failed"
            raise
        finally:
            finish_run(conn, run_id, status)


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunk Embeddings Pipeline")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="Behandl kun de første N chunks (til test)")
    parser.add_argument("--batch-size", type=int, default=32,
                        help="Antal chunks per embedding-kald (default: 32)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logger = _setup_logging(verbose=args.verbose)

    base_url = os.environ.get("EMBED_BASE_URL", DEFAULT_BASE_URL)
    logger.info(f"Venter på embed server: {base_url} ...")
    if not wait_for_server(base_url, timeout_s=120):
        logger.error(f"Embed server ikke tilgængelig: {base_url}")
        sys.exit(1)

    client = EmbedClient(base_url=base_url)
    logger.info(f"Model: {client.model} | Batch-size: {args.batch_size}")

    for attempt in range(1, MAX_RETRIES + 1):
        if attempt > 1:
            logger.warning(f"Genstart {attempt}/{MAX_RETRIES} om {RETRY_DELAY}s ...")
            time.sleep(RETRY_DELAY)
            if not wait_for_server(base_url, timeout_s=60):
                logger.error("Embed server nede ved genstart — afventer ...")
                continue

        try:
            t0 = time.monotonic()
            logger.info(f"Starter pipeline (forsøg {attempt}/{MAX_RETRIES})")
            _run_pipeline(args, client, logger)
            logger.info(f"Pipeline færdig. Total wall-time: {time.monotonic() - t0:.1f}s")
            return
        except Exception as exc:
            logger.error(f"Pipeline crashede: {exc}", exc_info=True)
            if attempt == MAX_RETRIES:
                logger.error("Max genstarter nået — stopper.")
                sys.exit(1)


if __name__ == "__main__":
    main()
