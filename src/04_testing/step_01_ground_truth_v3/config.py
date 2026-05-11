from __future__ import annotations

import os

CATEGORIES = [
    "fact_single",
    "summary",
    "reasoning",
    "unanswerable",
]

DEFAULT_PER_CATEGORY = 15
DEFAULT_WORKERS = 4
MAX_CHARS = 3000

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://teamragrats:ragrats@localhost:5433/ragrats",
)
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:8002/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "")
