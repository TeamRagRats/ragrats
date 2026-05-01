from __future__ import annotations

# Loads environment configuration from .env and exposes a frozen Config dataclass.
# Reads DATABASE_URL, DATA_ROOT, and ATTACHMENT_ROOT. Used by shared/db.py and run_ingest.py.

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    database_url: str
    data_root: Path
    attachment_root: Path
    repo_root: Path


def load_config() -> Config:
    repo_root = Path(__file__).resolve().parents[1]
    load_dotenv(repo_root / ".env")
    database_url = os.environ["DATABASE_URL"]
    data_root = Path(os.environ["DATA_ROOT"])
    attachment_root = Path(os.environ["ATTACHMENT_ROOT"])
    return Config(
        database_url=database_url,
        data_root=data_root,
        attachment_root=attachment_root,
        repo_root=repo_root,
    )
