from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg

from shared.config import load_config


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    cfg = load_config()
    with psycopg.connect(cfg.database_url) as conn:
        yield conn
