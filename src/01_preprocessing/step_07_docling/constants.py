from __future__ import annotations

# Constants for the docling pipeline. Ported from the old DuckDB-based pipeline in
# RagRats/src/Preprocessing/Step 4 — kept 1:1 so the proven batch/resource heuristics
# carry over to the new Postgres setup.

import re

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".pptx",
    ".html", ".htm", ".md",
    ".png", ".jpg", ".jpeg", ".tiff", ".bmp",
}

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
DOCUMENT_TIMEOUT_S = 300
LARGE_DOCUMENT_TIMEOUT_S = 1800
LARGE_FILE_THRESHOLD = 50 * 1024 * 1024
LIBREOFFICE_TIMEOUT_S = 120

# IN_270925-16344927_vedh1_REPORT.pdf  →  ("IN_270925-16344927", 1)
ATTACHMENT_PATTERN = re.compile(r"^((?:IN|OUT)_\d{6}-(?:REF)?\d+)_vedh(\d+)_")

GPU_MEM_WARN_PCT = 80
GPU_MEM_CRITICAL_PCT = 90
RAM_WARN_PCT = 80
RAM_CRITICAL_PCT = 90

# Container-side paths. docker-compose mounts:
#   data/attachments (host, ro)  -> /input
#   data            (host, rw)  -> /output
INPUT_ROOT = "/input"
LEGACY_DIR = "/output/attachments_legacy"
