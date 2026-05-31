from __future__ import annotations

# Constants for the docling pipeline. Ported from the old DuckDB-based pipeline in
# RagRats/src/Preprocessing/Step 4 — kept 1:1 so the proven batch/resource heuristics
# carry over to the new Postgres setup.

LEGACY_EXTENSIONS = {
    ".doc": "docx",
    ".xls": "xlsx",
    ".xlsm": "xlsx",
    ".ppt": "pptx",
    ".odt": "docx",
    ".ods": "xlsx",
    ".odp": "pptx",
}

BATCH_SIZE = 15
LIBREOFFICE_TIMEOUT_S = 120

GPU_MEM_WARN_PCT = 80
GPU_MEM_CRITICAL_PCT = 90
RAM_WARN_PCT = 80
RAM_CRITICAL_PCT = 90

# Container-side paths. docker-compose mounts:
#   data/attachments (host, ro)  -> /input
#   data            (host, rw)  -> /output
INPUT_ROOT = "/input"
LEGACY_DIR = "/output/attachments_legacy"
