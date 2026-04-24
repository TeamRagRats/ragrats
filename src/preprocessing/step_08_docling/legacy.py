from __future__ import annotations

# Converts legacy Office formats (.doc/.xls/.xlsm/.ppt/.odt/.ods/.odp) to modern
# equivalents via LibreOffice headless. Outputs go to LEGACY_DIR (persistent cache
# across runs). Sequential execution is intentional — LO's global lock file makes
# parallel calls unreliable.

import hashlib
import logging
import shutil
import subprocess
from pathlib import Path

from step_08_docling.constants import (
    LEGACY_DIR,
    LEGACY_EXTENSIONS,
    LIBREOFFICE_TIMEOUT_S,
)
from step_08_docling.queue import QueueItem


def convert_legacy_files(
    tasks: list[QueueItem], logger: logging.Logger
) -> list[QueueItem]:
    lo_bin = shutil.which("libreoffice") or shutil.which("soffice")
    legacy_count = sum(1 for t in tasks if t.file_type in LEGACY_EXTENSIONS)
    if legacy_count == 0:
        return tasks

    if not lo_bin:
        logger.warning(
            f"LibreOffice not found — {legacy_count} legacy files skipped"
        )
        return [t for t in tasks if t.file_type not in LEGACY_EXTENSIONS]

    out_dir = Path(LEGACY_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    updated: list[QueueItem] = []
    converted = cached = failed = 0

    for task in tasks:
        if task.file_type not in LEGACY_EXTENSIONS:
            updated.append(task)
            continue

        target_fmt = LEGACY_EXTENSIONS[task.file_type]
        # Stable cache key based on source path so re-runs hit the cache.
        path_hash = hashlib.md5(str(task.container_path).encode()).hexdigest()[:8]
        cached_path = out_dir / f"{path_hash}_{task.container_path.stem}.{target_fmt}"

        if cached_path.exists():
            task.container_path = cached_path
            task.file_type = f".{target_fmt}"
            updated.append(task)
            cached += 1
            continue

        try:
            result = subprocess.run(
                [lo_bin, "--headless", "--norestore",
                 "--convert-to", target_fmt,
                 "--outdir", str(out_dir),
                 str(task.container_path)],
                capture_output=True, text=True,
                timeout=LIBREOFFICE_TIMEOUT_S,
            )
            lo_output = out_dir / f"{task.container_path.stem}.{target_fmt}"
            if result.returncode == 0 and lo_output.exists():
                lo_output.rename(cached_path)
                task.container_path = cached_path
                task.file_type = f".{target_fmt}"
                updated.append(task)
                converted += 1
                logger.debug(f"Converted: {task.container_path.name}")
            else:
                logger.warning(
                    f"LibreOffice failed: {task.container_path.name} — "
                    f"{result.stderr.strip()[:200]}"
                )
                failed += 1
        except subprocess.TimeoutExpired:
            logger.warning(f"LibreOffice timeout: {task.container_path.name}")
            failed += 1
        except Exception as exc:
            logger.warning(f"LibreOffice error: {task.container_path.name} — {exc}")
            failed += 1

    logger.info(
        f"Legacy conversion: {converted} converted, {cached} cached, {failed} failed"
    )
    return updated
