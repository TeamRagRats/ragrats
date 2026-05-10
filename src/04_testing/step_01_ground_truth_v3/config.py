from __future__ import annotations

import os

CATEGORIES = [
    "fact_single",
    "summary",
    "multi_context",
    "reasoning",
    "unanswerable",
    "generic",
]

DEFAULT_QA_PER_CHUNK = 3
DEFAULT_TARGET_PER_VOYAGE = 50
DEFAULT_WORKERS = 4
CHUNK_BUFFER_MULTIPLIER = 3
MAX_CHARS = 3000

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://teamragrats:ragrats@localhost:5433/ragrats",
)
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:8002/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "")
