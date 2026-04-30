from __future__ import annotations

# Context manager that opens a psycopg connection using the Config from core/config.py.
# Used by run_ingest.py, run_summaries.py, sql_migrations/migrate.py, and core/logging/ingest_summary.py.

from contextlib import contextmanager
from typing import Iterator

import psycopg

from core.config import load_config


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    cfg = load_config()
    with psycopg.connect(cfg.database_url) as conn:
        yield conn
