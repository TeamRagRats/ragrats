from __future__ import annotations

# Step 8 entry point. Reads pending sha256s from llm_load_queue, categorises by
# char_count into small/medium/large/huge, and processes each tier sequentially
# with the worker counts in step_08_llm_extraction.constants. Workers run the
# LLM call concurrently; the main thread is the only one writing to Postgres.
#
# Run (from inside the vLLM-reachable environment):
#   python3 -m preprocessing.run_llm_extraction --resume

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _repo_root = _here.parents[1]
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_here))
    __package__ = "preprocessing"

import argparse
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from core.db import connect
from log.log_run import finish_run, start_run, step
from log.log_llm_extraction import (
    log_extraction_pending,
    log_extraction_finished,
    reset_extraction_errors,
)
from clients.llm_client import DEFAULT_BASE_URL, LLMClient, wait_for_server
from step_07_docling.resources import (
    cleanup_memory,
    get_gpu_info,
    get_ram_info,
    log_resource_status,
)
from step_08_llm_extraction import db as ldb
from step_08_llm_extraction.constants import (
    BATCH_SIZE,
    DEFAULT_CLASSIFY_THRESHOLD,
    FULL_MAX_TOKENS,
    GPU_MEM_CRITICAL_PCT,
    GPU_MEM_WARN_PCT,
    RAM_CRITICAL_PCT,
    RAM_WARN_PCT,
    WORKERS_BY_TIER,
    categorize,
)
from step_08_llm_extraction.extractor import ExtractionResult, process_single_document


def _setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("llm_extraction")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


def _adjust_batch_size(batch_size: int, resources: dict, logger: logging.Logger) -> int:
    gpu = resources.get("gpu")
    if gpu:
        pct = gpu["mem_used_pct"]
        if pct > GPU_MEM_CRITICAL_PCT:
            new = max(5, batch_size - 5)
            if new != batch_size:
                logger.warning(f"GPU mem critical ({pct}%) — batch {batch_size}→{new}")
                batch_size = new
        elif pct > GPU_MEM_WARN_PCT:
            new = max(10, batch_size - 2)
            if new != batch_size:
                logger.warning(f"GPU mem high ({pct}%) — batch {batch_size}→{new}")
                batch_size = new
    ram = resources.get("ram")
    if ram:
        pct = ram["used_pct"]
        if pct > RAM_CRITICAL_PCT:
            new = max(5, batch_size - 5)
            if new != batch_size:
                logger.warning(f"RAM critical ({pct}%) — batch {batch_size}→{new}")
                batch_size = new
        elif pct > RAM_WARN_PCT:
            new = max(10, batch_size - 2)
            if new != batch_size:
                logger.warning(f"RAM high ({pct}%) — batch {batch_size}→{new}")
                batch_size = new
    return batch_size


def _fmt_time(s: float) -> str:
    if s < 60:
        return f"{s:.0f}s"
    if s < 3600:
        return f"{s / 60:.1f} min"
    h, m = int(s // 3600), int((s % 3600) // 60)
    return f"{h}h {m:02d}m"


def _print_preflight(logger: logging.Logger, by_tier: dict[str, list[ldb.QueueItem]]) -> None:
    logger.info("=" * 60)
    logger.info("LLM EXTRACTION PRE-FLIGHT")
    logger.info("=" * 60)
    total = sum(len(v) for v in by_tier.values())
    logger.info(f"  Pending total: {total}")
    for tier in ("small", "medium", "large", "huge"):
        items = by_tier.get(tier, [])
        logger.info(f"    {tier:>6s}: {len(items):>4d}  (workers={WORKERS_BY_TIER[tier]})")
    log_resource_status(logger)
    logger.info("=" * 60)


def _process_batch(
    conn,
    llm: LLMClient,
    batch: list[ldb.QueueItem],
    tier: str,
    workers: int,
    classify_threshold: int,
    full_max_tokens: int,
    temperature: float,
    batch_idx: int,
    run_id,
    logger: logging.Logger,
    pending_total: int,
    done_so_far: int,
) -> tuple[int, int, int]:
    # Mark every item pending in the main thread before the executor starts so a
    # mid-batch crash leaves accurate state in llm_logging.
    started = datetime.now(timezone.utc)
    for item in batch:
        size_cat = categorize(item.char_count)
        mode_pre = "classify" if (
            classify_threshold != -1 and item.char_count >= classify_threshold
        ) else "full"
        log_extraction_pending(
            conn,
            sha256=item.sha256,
            file_path=item.file_path,
            file_type=item.file_type,
            char_count=item.char_count,
            size_category=size_cat,
            mode=mode_pre,
            started_at=started,
            run_id=run_id,
            batch_idx=batch_idx,
        )

    # Per-row DB writes inside as_completed: each finished doc is persisted
    # before the next future is awaited. Otherwise a 6-min batch leaves all
    # 15 rows 'pending' and the watchdog (10-min stuck threshold) kills the
    # orchestrator before any DB write lands.
    # Thread-safe: only the main thread (this loop) ever touches `conn`.
    done = errors = skipped = 0
    gpu = get_gpu_info()
    ram = get_ram_info()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(
                process_single_document, item, llm,
                classify_threshold, full_max_tokens, temperature,
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

            log_extraction_finished(
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
                logger.info(
                    f"  [{tier} {idx}/{pending_total}] {res.sha256[:12]} "
                    f"mode={res.mode} chars={item.char_count} "
                    f"in={res.input_tokens} out={res.output_tokens} "
                    f"({res.duration_s:.1f}s)"
                )
            elif res.status == "skipped":
                logger.warning(
                    f"  [{tier} {idx}/{pending_total}] {res.sha256[:12]} "
                    f"SKIP — {res.error_message}"
                )
            else:
                logger.error(
                    f"  [{tier} {idx}/{pending_total}] {res.sha256[:12]} "
                    f"ERR — {res.error_message}"
                )

    return done, errors, skipped


def _process_tier(
    conn,
    llm: LLMClient,
    tier: str,
    items: list[ldb.QueueItem],
    args: argparse.Namespace,
    run_id,
    logger: logging.Logger,
) -> tuple[int, int, int]:
    if not items:
        logger.info(f"[{tier}] empty.")
        return 0, 0, 0

    workers = WORKERS_BY_TIER[tier]
    if args.max_workers is not None:
        workers = min(workers, args.max_workers)

    batch_size = args.batch_size
    total_done = total_err = total_skip = 0
    processed = 0
    pending_total = len(items)

    logger.info(f"\n=== Tier: {tier}  ({pending_total} files, workers={workers}) ===")

    while processed < pending_total:
        batch = items[processed:processed + batch_size]
        batch_idx = (processed // max(batch_size, 1)) + 1
        logger.info(
            f"--- {tier} batch {batch_idx} "
            f"({len(batch)} files, batch_size={batch_size}) ---"
        )

        done, errs, skipped = _process_batch(
            conn, llm, batch, tier, workers,
            args.classify_threshold, args.max_tokens, args.temperature,
            batch_idx, run_id, logger, pending_total,
            total_done + total_err + total_skip,
        )
        total_done += done
        total_err += errs
        total_skip += skipped
        processed += len(batch)

        cleanup_memory(logger)
        resources = log_resource_status(logger)
        batch_size = _adjust_batch_size(batch_size, resources, logger)

    logger.info(
        f"[{tier}] done. {total_done} ok / {total_err} err / {total_skip} skipped"
    )
    return total_done, total_err, total_skip


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Step 8 — LLM extraction (FULL + CLASSIFY) on Docling markdown."
    )
    parser.add_argument("--limit", type=int, default=None, metavar="N")
    parser.add_argument("--voyage", type=str, default=None, help="Filter by voyage_key")
    parser.add_argument("--sha256", action="append", default=[], metavar="HASH",
                        help="Process only the listed sha256(s). Repeatable.")
    parser.add_argument("--fresh", action="store_true",
                        help="Delete error rows in llm_logging for matching sha256s "
                             "before fetching pending.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Categorise + report without LLM calls.")
    parser.add_argument("--max-tokens", type=int, default=FULL_MAX_TOKENS,
                        help="Output token budget for FULL mode.")
    parser.add_argument("--classify-threshold", type=int, default=DEFAULT_CLASSIFY_THRESHOLD,
                        help="Char-count above which CLASSIFY mode is used (-1 disables).")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--max-workers", type=int, default=None,
                        help="Cap workers across all tiers.")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logger = _setup_logging(verbose=args.verbose)

    base_url = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL)
    if not args.dry_run:
        logger.info(f"Waiting for vLLM server: {base_url}")
        if not wait_for_server(base_url, timeout_s=600):
            logger.error(f"vLLM server not reachable: {base_url}")
            sys.exit(1)
        llm = LLMClient(base_url=base_url)
        logger.info(f"Model: {llm.model}")
    else:
        llm = None  # type: ignore[assignment]

    sha_filter = {h.lower() for h in args.sha256} if args.sha256 else None

    with connect() as conn:
        run_id = start_run(conn)
        status = "ok"
        t_start = time.monotonic()
        try:
            if args.fresh:
                deleted = ldb.reset_errors(conn, sha_filter)
                logger.info(f"--fresh: deleted {deleted} error row(s) in llm_logging.")

            pending = ldb.fetch_pending(
                conn,
                voyage=args.voyage,
                sha256_filter=sha_filter,
                limit=args.limit,
            )

            if not pending:
                logger.info("Nothing pending — exiting.")
                return

            by_tier: dict[str, list[ldb.QueueItem]] = {
                "small": [], "medium": [], "large": [], "huge": []
            }
            for item in pending:
                by_tier[categorize(item.char_count)].append(item)

            _print_preflight(logger, by_tier)

            if args.dry_run:
                logger.info("--dry-run: stopping before any LLM calls.")
                return

            grand_done = grand_err = grand_skip = 0
            assert llm is not None  # narrowed: dry-run already returned above
            for tier in ("small", "medium", "large", "huge"):
                items = by_tier[tier]
                if not items:
                    continue
                with step(conn, run_id, f"llm_extraction_{tier}") as timer:
                    timer.rows_in = len(items)
                    done, errs, skipped = _process_tier(
                        conn, llm, tier, items, args, run_id, logger
                    )
                    timer.rows_out = done
                    timer.errors = errs
                grand_done += done
                grand_err += errs
                grand_skip += skipped

            logger.info(
                f"\nAll tiers done. {grand_done} ok / {grand_err} err / "
                f"{grand_skip} skipped / total {_fmt_time(time.monotonic() - t_start)}"
            )
        except Exception:
            status = "failed"
            raise
        finally:
            finish_run(conn, run_id, status)


if __name__ == "__main__":
    main()
