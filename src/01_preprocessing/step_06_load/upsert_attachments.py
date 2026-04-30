from __future__ import annotations

# Replaces all attachment rows for an email (delete + insert) in the attachments table.
# Stores file_path relative to repo root. Called per-email in run_ingest.py after extract_attachments.

from pathlib import Path
from typing import Iterable
from uuid import UUID

import psycopg

from step_05_attachments.extract_attachments import WrittenAttachment

_DELETE = "DELETE FROM attachments WHERE email_id = %s"
_INSERT = """
INSERT INTO attachments (
    email_id, voyage_key, file_name, file_path, file_type,
    size_bytes, sha256, docling_ready
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""


def upsert_attachments(
    cur: psycopg.Cursor,
    email_id: UUID,
    voyage_key: str,
    attachments: Iterable[WrittenAttachment],
    repo_root: Path,
) -> None:
    cur.execute(_DELETE, (str(email_id),))
    for a in attachments:
        # Store file_path relative to repo root if possible
        try:
            file_path = str(a.file_path.relative_to(repo_root))
        except ValueError:
            file_path = str(a.file_path)

        cur.execute(
            _INSERT,
            (
                str(email_id),
                voyage_key,
                a.file_name,
                file_path,
                a.file_type,
                a.size_bytes,
                a.sha256,
                a.docling_ready,
            ),
        )
