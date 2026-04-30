from __future__ import annotations

# Rerun LLM extraction for documents whose output was cut off by the token cap.
# Queries llm_structured for rows where output_token_count matches one of the
# known cap values (default: 5000, 8196) and reruns them with a higher budget.
#
# Assumes vLLM is already running. Start it with:
#   docker compose -f docker/vllm/docker-compose.yml up -d
#
# Usage:
#   python3 src/preprocessing/rerun_token_limited.py --dry-run
#   python3 src/preprocessing/rerun_token_limited.py --limit 10 --verbose
#   python3 src/preprocessing/rerun_token_limited.py
#   python3 src/preprocessing/rerun_token_limited.py --sha256 abc123 --sha256 def456

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _repo_root = _here.parents[2]
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_here.parent))
    __package__ = "preprocessing"

import argparse
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

import psycopg

from core.db import connect
from core.logging.run_logger import finish_run, start_run
from step_07_docling.resources import cleanup_memory, get_gpu_info, get_ram_info
from clients.llm_client import DEFAULT_BASE_URL, LLMClient, wait_for_server
from step_08_llm_extraction import db as ldb
from step_08_llm_extraction.constants import DEFAULT_CLASSIFY_THRESHOLD, categorize
from step_08_llm_extraction.extractor import ExtractionResult, process_single_document

DEFAULT_MAX_TOKENS = 16_000
DEFAULT_TOKEN_LIMITS = (5000, 8196, 16000)
DEFAULT_WORKERS = 4
DEFAULT_BATCH_SIZE = 10
DEFAULT_FULL_TIMEOUT = 150  # seconds per SHA; on timeout falls back to classify


def _setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("rerun_token_limited")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


def _get_maxed_sha256s(conn: psycopg.Connection, token_limits: tuple[int, ...]) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT sha256 FROM llm_structured "
            "WHERE output_token_count = ANY(%s) AND mode = 'full'",
            (list(token_limits),),
        )
        return [row[0] for row in cur.fetchall()]


def _process_with_cap(
    item: ldb.QueueItem,
    llm: Optional[LLMClient],
    classify_threshold: int,
    full_max_tokens: int,
    temperature: float,
    full_timeout_s: float,
) -> ExtractionResult:
    """Run process_single_document with a wall-clock cap.

    If the full-mode call exceeds `full_timeout_s` seconds, the thread is
    abandoned (daemon) and classify mode runs immediately as fallback.
    classify_threshold=0 forces classify because item.char_count < 0 is always False.
    """
    result_holder: list[ExtractionResult] = []

    def _run() -> None:
        result_holder.append(
            process_single_document(item, llm, classify_threshold, full_max_tokens, temperature)
        )

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=full_timeout_s)

    if result_holder:
        return result_holder[0]

    # Timed out — run classify as fallback in the current thread
    res = process_single_document(item, llm, 0, full_max_tokens, temperature)
    if res.status == "done":
        res.error_message = f"fallback_classify: full timed out after {int(full_timeout_s)}s"
    return res


def _process_batch(
    conn,
    llm: Optional[LLMClient],
    batch: list[ldb.QueueItem],
    workers: int,
    classify_threshold: int,
    full_max_tokens: int,
    temperature: float,
    batch_idx: int,
    run_id,
    logger: logging.Logger,
    total: int,
    done_so_far: int,
    dry_run: bool,
    full_timeout_s: float = DEFAULT_FULL_TIMEOUT,
) -> tuple[int, int, int]:
    started = datetime.now(timezone.utc)

    for item in batch:
        size_cat = categorize(item.char_count)
        mode_pre = (
            "classify"
            if (classify_threshold != -1 and item.char_count >= classify_threshold)
            else "full"
        )
        if not dry_run:
            ldb.log_pending(conn, item, size_cat, mode_pre, started, run_id, batch_idx)

    if dry_run:
        for item in batch:
            logger.info(f"  [DRY-RUN] {item.sha256[:12]}... chars={item.char_count}")
        return len(batch), 0, 0

    gpu = get_gpu_info()
    ram = get_ram_info()
    done = errors = skipped = 0

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(
                _process_with_cap, item, llm,
                classify_threshold, full_max_tokens, temperature, full_timeout_s,
            ): item
            for item in batch
        }
        for fut in as_completed(futures):
            item = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:
                res = ExtractionResult(
                    sha256=item.sha256, mode="full", status="error",
                    error_message=f"{type(exc).__name__}: {exc}",
                    started_at=started, finished_at=datetime.now(timezone.utc),
                )

            if res.status == "done":
                ldb.upsert_structured(
                    conn,
                    sha256=res.sha256,
                    mode=res.mode,
                    document_type=res.document_type,
                    structured_md=res.structured_md,
                    input_token_count=res.input_tokens,
                    output_token_count=res.output_tokens,
                    model_name=llm.model,
                )
                done += 1
            elif res.status == "skipped":
                skipped += 1
            else:
                errors += 1

            ldb.log_finished(
                conn,
                sha256=res.sha256,
                finished_at=res.finished_at or datetime.now(timezone.utc),
                duration_ms=int(res.duration_s * 1000),
                status=res.status,
                error_message=res.error_message,
                input_tokens=res.input_tokens or None,
                output_tokens=res.output_tokens or None,
                gpu_util_pct=gpu["gpu_util_pct"] if gpu else None,
                gpu_mem_pct=gpu["mem_used_pct"] if gpu else None,
                ram_pct=ram["used_pct"] if ram else None,
            )

            idx = done_so_far + done + errors + skipped
            if res.status == "done":
                if res.error_message:
                    logger.warning(
                        f"  [{idx}/{total}] {res.sha256[:12]} note={res.error_message}"
                    )
                logger.info(
                    f"  [{idx}/{total}] {res.sha256[:12]} "
                    f"mode={res.mode} chars={item.char_count} "
                    f"in={res.input_tokens} out={res.output_tokens} "
                    f"({res.duration_s:.1f}s)"
                )
            elif res.status == "skipped":
                logger.warning(
                    f"  [{idx}/{total}] {res.sha256[:12]} SKIP — {res.error_message}"
                )
            else:
                logger.error(
                    f"  [{idx}/{total}] {res.sha256[:12]} ERR — {res.error_message}"
                )

    return done, errors, skipped


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Rerun LLM extraction for documents whose output hit the token cap. "
            "Auto-discovers targets from llm_structured; vLLM must already be running."
        )
    )
    parser.add_argument(
        "--sha256", action="append", default=[], metavar="HASH",
        help="Additional sha256 to include (repeatable; merged with auto-discovered set).",
    )
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="Cap total documents to process.")
    parser.add_argument(
        "--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
        help=f"Output token budget for FULL mode (default: {DEFAULT_MAX_TOKENS}).",
    )
    parser.add_argument(
        "--token-limits", type=str,
        default=",".join(str(t) for t in DEFAULT_TOKEN_LIMITS),
        metavar="A,B,...",
        help=(
            "Comma-separated output_token_count values treated as 'capped'. "
            f"Default: {','.join(str(t) for t in DEFAULT_TOKEN_LIMITS)}."
        ),
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument(
        "--classify-threshold", type=int, default=DEFAULT_CLASSIFY_THRESHOLD,
        help="Char-count above which CLASSIFY mode is used (-1 disables).",
    )
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument(
        "--full-timeout", type=int, default=DEFAULT_FULL_TIMEOUT,
        metavar="SEC",
        help=(
            f"Wall-clock cap in seconds for full-mode LLM call per SHA "
            f"(default: {DEFAULT_FULL_TIMEOUT}). On timeout, falls back to classify."
        ),
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Discover and log targets without making any LLM calls.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logger = _setup_logging(verbose=args.verbose)

    try:
        token_limits = tuple(
            int(x.strip()) for x in args.token_limits.split(",") if x.strip()
        )
    except ValueError:
        logger.error(
            f"--token-limits must be comma-separated integers, got: {args.token_limits}"
        )
        sys.exit(1)

    base_url = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL)
    if not args.dry_run:
        logger.info(f"Waiting for vLLM server: {base_url}")
        if not wait_for_server(base_url, timeout_s=600):
            logger.error(f"vLLM server not reachable: {base_url}")
            sys.exit(1)
        llm = LLMClient(base_url=base_url)
        logger.info(f"Model: {llm.model}")
    else:
        llm = None

    with connect() as conn:
        auto_shas = _get_maxed_sha256s(conn, token_limits)
        logger.info(
            f"Auto-discovered {len(auto_shas)} sha256(s) with "
            f"output_token_count in {token_limits}."
        )

        manual_shas = {h.lower() for h in args.sha256}
        sha_set = set(auto_shas) | manual_shas
        if manual_shas:
            logger.info(f"  + {len(manual_shas)} manually specified sha256(s).")

        if not sha_set:
            logger.info("Nothing to rerun. Exiting.")
            return

        items = ldb.fetch_pending(conn, sha256_filter=sha_set, include_done=True)
        logger.info(
            f"Fetched {len(items)} document(s) from queue."
        )

        if args.limit and len(items) > args.limit:
            items = items[: args.limit]
            logger.info(f"Applying --limit: capped to {len(items)} document(s).")

        total = len(items)
        if not total:
            logger.info("All target sha256s missing from llm_load_queue. Nothing to do.")
            return

        logger.info(
            f"Starting rerun: {total} docs, max_tokens={args.max_tokens}, "
            f"workers={args.max_workers}, batch_size={args.batch_size}"
            + (" [DRY-RUN]" if args.dry_run else "")
        )

        run_id = None if args.dry_run else start_run(conn)
        total_done = total_err = total_skip = 0
        processed = 0
        batch_size = args.batch_size
        t_start = time.monotonic()
        status = "ok"

        try:
            while processed < total:
                batch = items[processed : processed + batch_size]
                batch_idx = (processed // max(batch_size, 1)) + 1
                logger.info(f"--- batch {batch_idx} ({len(batch)} docs) ---")

                done, errs, skipped = _process_batch(
                    conn, llm, batch,
                    workers=args.max_workers,
                    classify_threshold=args.classify_threshold,
                    full_max_tokens=args.max_tokens,
                    temperature=args.temperature,
                    batch_idx=batch_idx,
                    run_id=run_id,
                    logger=logger,
                    total=total,
                    done_so_far=total_done + total_err + total_skip,
                    dry_run=args.dry_run,
                    full_timeout_s=args.full_timeout,
                )
                total_done += done
                total_err += errs
                total_skip += skipped
                processed += len(batch)

                if not args.dry_run:
                    cleanup_memory(logger)
        except Exception:
            status = "failed"
            raise
        finally:
            if run_id is not None:
                finish_run(conn, run_id, status=status)

        elapsed = time.monotonic() - t_start
        logger.info(
            f"\nDone. {total_done} ok / {total_err} err / {total_skip} skipped "
            f"— {elapsed:.1f}s total"
        )
        if total_err:
            sys.exit(1)


if __name__ == "__main__":
    main()
