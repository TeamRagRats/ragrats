import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://teamragrats:ragrats@localhost:5433/ragrats",
)
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:8002/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "")  # empty = auto-detect from server

CATEGORIES = ["logistics_cargo", "commercial_terms", "incident_decision"]

DEFAULT_TARGET_PER_VOYAGE = 50   # 20 voyages × 50 = 1000 total
DEFAULT_WORKERS = 4
CHUNK_BUFFER_MULTIPLIER = 3      # sample 3× target to hit pass rate
MAX_CHUNKS_PER_SOURCE_TYPE = 10  # stratification cap per source_type
