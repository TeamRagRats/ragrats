from __future__ import annotations

# Entry point for the docling pipeline (step 8). Reads files from the
# docling_load_queue view, converts them with Docling inside the ragrats_docling
# GPU container, and writes results to docling + docling_logging.
#
# The converter is configured for high-quality output: ACCURATE table mode +
# do_cell_matching, do_picture_description with IBM Granite Vision 3.3-2b as the
# local VLM, and the Heron layout model when available. Sequential — no parallel
# workers. The --sha256 flag (repeatable) re-processes specific files without
# manually clearing DB rows.
#
# Run (inside the container):
#   python3 -m preprocessing.run_docling --resume --voyage <key>

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
import sys
import time
from datetime import datetime, timezone

from shared.db import connect
from shared.logging.run_logger import finish_run, start_run
from step_08_docling import db as ddb
from step_08_docling.constants import (
    BATCH_SIZE,
    GPU_MEM_CRITICAL_PCT,
    GPU_MEM_WARN_PCT,
    RAM_CRITICAL_PCT,
    RAM_WARN_PCT,
)
from step_08_docling.docling_runner import build_docling_converter, process_single_file
from step_08_docling.legacy import convert_legacy_files
from step_08_docling.job_queue import QueueItem, fetch_queue, queue_stats
from step_08_docling.resources import (
    check_cuda_available,
    cleanup_memory,
    get_gpu_info,
    get_ram_info,
    log_resource_status,
)


def _setup_logging(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("docling")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


def _print_preflight(logger: logging.Logger, stats: dict, cuda: dict) -> None:
    logger.info("=" * 60)
    logger.info("DOCLING PRE-FLIGHT")
    logger.info("=" * 60)
    logger.info(f"  Queue total:   {stats['total']}")
    for ext, n in stats["by_type"].items():
        logger.info(f"    {str(ext):>10s}: {n}")
    logger.info(f"  CUDA available: {cuda['cuda_available']}")
    logger.info(f"  Driver:         {cuda['driver_version']}")
    logger.info(f"  CUDA version:   {cuda['cuda_version']}")
    log_resource_status(logger)
    logger.info("=" * 60)


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


def _process_batch(
    conn,
    converter,
    batch: list[QueueItem],
    batch_idx: int,
    run_id,
    logger: logging.Logger,
) -> tuple[int, int]:
    done = errors = 0
    for i, task in enumerate(batch, 1):
        size_kb = round(task.container_path.stat().st_size / 1024, 1) if task.container_path.exists() else 0
        logger.info(f"  [{i}/{len(batch)}] {task.container_path.name} ({size_kb} KB)")

        started = datetime.now(timezone.utc)
        ddb.log_file_pending(
            conn,
            sha256=task.sha256,
            file_path=task.file_path,
            file_type=task.file_type,
            file_size_bytes=task.container_path.stat().st_size if task.container_path.exists() else 0,
            started_at=started,
            run_id=run_id,
            batch_idx=batch_idx,
        )

        result = process_single_file(task, converter)

        if result.status == "done":
            ddb.upsert_docling(
                conn,
                sha256=result.sha256,
                markdown=result.markdown,
                char_count=result.char_count,
                token_count=result.token_count,
            )
            done += 1
            logger.info(f"    ok — {result.char_count} chars, {result.duration_s}s")
        else:
            errors += 1
            logger.warning(f"    err — {result.error_message}")

        gpu = get_gpu_info()
        ram = get_ram_info()
        ddb.log_file_finished(
            conn,
            sha256=result.sha256,
            finished_at=result.finished_at or datetime.now(timezone.utc),
            duration_ms=int(result.duration_s * 1000),
            status=result.status,
            error_message=result.error_message,
            char_count=result.char_count,
            token_count=result.token_count,
            gpu_util_pct=gpu["gpu_util_pct"] if gpu else None,
            gpu_mem_pct=gpu["mem_used_pct"] if gpu else None,
            ram_pct=ram["used_pct"] if ram else None,
        )

        # Free large objects before next file.
        result.markdown = None

    return done, errors


def _fmt_time(s: float) -> str:
    if s < 60:
        return f"{s:.0f}s"
    if s < 3600:
        return f"{s / 60:.1f} min"
    h, m = int(s // 3600), int((s % 3600) // 60)
    return f"{h}h {m:02d}m"


def main() -> None:
    parser = argparse.ArgumentParser(description="Docling pipeline — sequential, ACCURATE + picture description")
    parser.add_argument("--limit", type=int, default=None, metavar="N")
    parser.add_argument("--voyage", type=str, default=None, help="Filter by voyage_key")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--resume", action="store_true",
                        help="Skip files already marked status='done' in docling_logging "
                             "(ignored when --sha256 is set so test re-runs always execute).")
    parser.add_argument("--sha256", action="append", default=[], metavar="HASH",
                        help="Process only the listed sha256(s). Repeatable. Implies --resume=False.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logger = _setup_logging(verbose=args.verbose)

    with connect() as conn:
        run_id = start_run(conn)
        status = "ok"
        t_start = time.monotonic()
        try:
            stats = queue_stats(conn, voyage=args.voyage)
            cuda = check_cuda_available()
            _print_preflight(logger, stats, cuda)

            sha_filter = {h.lower() for h in args.sha256} if args.sha256 else None
            effective_resume = args.resume and not sha_filter

            tasks = fetch_queue(conn, voyage=args.voyage, resume=effective_resume, limit=args.limit)

            if sha_filter:
                tasks = [t for t in tasks if t.sha256.lower() in sha_filter]
                missing = sha_filter - {t.sha256.lower() for t in tasks}
                if missing:
                    logger.warning(
                        "sha256 filter: %d hash(es) not found in docling_load_queue: %s",
                        len(missing), ", ".join(sorted(missing))
                    )
                logger.info("sha256 filter active — %d task(s) will run (resume forced off).", len(tasks))

            if not tasks:
                logger.info("Queue empty — nothing to process.")
                return
            logger.info(
                f"Fetched {len(tasks)} tasks (resume={effective_resume}, "
                f"limit={args.limit}, voyage={args.voyage}, sha256_filter={bool(sha_filter)})"
            )

            tasks = convert_legacy_files(tasks, logger)
            if not tasks:
                logger.info("No tasks left after legacy filtering.")
                return

            logger.info("Initialising Docling converter ...")
            converter = build_docling_converter()
            logger.info("Converter ready.")

            batch_size = args.batch_size
            total_done = total_errors = 0
            processed = 0

            while processed < len(tasks):
                batch = tasks[processed:processed + batch_size]
                batch_idx = (processed // max(batch_size, 1)) + 1
                logger.info(f"\n--- Batch {batch_idx} ({len(batch)} files, batch_size={batch_size}) ---")

                done, errs = _process_batch(conn, converter, batch, batch_idx, run_id, logger)
                total_done += done
                total_errors += errs
                processed += len(batch)

                cleanup_memory(logger)
                resources = log_resource_status(logger)
                batch_size = _adjust_batch_size(batch_size, resources, logger)

                elapsed = time.monotonic() - t_start
                rate = elapsed / processed if processed else 0
                eta = rate * (len(tasks) - processed)
                logger.info(
                    f"  progress: {processed}/{len(tasks)} "
                    f"({total_done} ok, {total_errors} err) | eta {_fmt_time(eta)}"
                )

            logger.info(
                f"\nDone. {total_done} ok / {total_errors} err / "
                f"total {_fmt_time(time.monotonic() - t_start)}"
            )
        except Exception:
            status = "failed"
            raise
        finally:
            finish_run(conn, run_id, status)


if __name__ == "__main__":
    main()
