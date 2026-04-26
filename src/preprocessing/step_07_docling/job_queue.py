from __future__ import annotations

# Reads unique files to process from the docling_load_queue view, maps the stored
# (repo-relative) file_path to the container-side /input path, and optionally skips
# files already marked status='done' in docling_logging when --resume is set.

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import psycopg

from step_07_docling.constants import ATTACHMENT_PATTERN, INPUT_ROOT


@dataclass
class QueueItem:
    sha256: str
    email_id: str
    voyage_key: str
    file_path: str         # original (repo-relative) path as stored in DB
    file_type: str         # extension incl. dot, e.g. ".pdf"
    container_path: Path   # resolved path inside the container (/input/...)
    email_ref: str = ""    # e.g. "IN_270925-16344927"
    attachment_num: int = 0


def _to_container_path(db_path: str) -> Path:
    # DB stores paths relative to repo root, e.g. "data/attachments/<voyage>/<file>".
    # The container mounts host data/attachments -> /input, so strip the prefix.
    p = db_path.replace("\\", "/")
    for prefix in ("data/attachments/", "data/attachment/", "attachments/", "attachment/"):
        if p.startswith(prefix):
            return Path(INPUT_ROOT) / p[len(prefix):]
    # Fallback: assume the path is already relative to the attachments root.
    return Path(INPUT_ROOT) / p.lstrip("/")


def _parse_email_ref(filename: str) -> tuple[str, int]:
    m = ATTACHMENT_PATTERN.match(filename)
    if m:
        return m.group(1), int(m.group(2))
    return "", 0


def fetch_queue(
    conn: psycopg.Connection,
    voyage: Optional[str] = None,
    resume: bool = True,
    limit: Optional[int] = None,
) -> list[QueueItem]:
    from psycopg import sql as pgsql

    parts: list[pgsql.Composable] = [pgsql.SQL(
        "SELECT q.sha256, q.email_id, q.voyage_key, q.file_path, q.file_type "
        "FROM docling_load_queue q "
    )]
    params: list = []
    if resume:
        parts.append(pgsql.SQL(
            "LEFT JOIN docling_logging l ON l.sha256 = q.sha256 "
            "WHERE (l.status IS NULL OR l.status <> 'done') "
        ))
    else:
        parts.append(pgsql.SQL("WHERE TRUE "))

    if voyage:
        parts.append(pgsql.SQL("AND q.voyage_key = %s "))
        params.append(voyage)

    parts.append(pgsql.SQL("ORDER BY q.sha256 "))
    if limit:
        parts.append(pgsql.SQL("LIMIT %s"))
        params.append(limit)

    items: list[QueueItem] = []
    with conn.cursor() as cur:
        cur.execute(pgsql.Composed(parts), params)
        for sha, email_id, voyage_key, file_path, file_type in cur.fetchall():
            cpath = _to_container_path(file_path)
            ref, num = _parse_email_ref(cpath.name)
            # file_type in DB is MIME (application/pdf); docling/legacy logic needs
            # the filename extension, so prefer suffix and fall back to the stored value.
            ext = cpath.suffix.lower() or (file_type or "").lower()
            items.append(QueueItem(
                sha256=sha,
                email_id=str(email_id),
                voyage_key=voyage_key,
                file_path=file_path,
                file_type=ext,
                container_path=cpath,
                email_ref=ref,
                attachment_num=num,
            ))
    return items


def queue_stats(conn: psycopg.Connection, voyage: Optional[str] = None) -> dict:
    params = (voyage,) if voyage else ()
    with conn.cursor() as cur:
        if voyage:
            cur.execute("SELECT COUNT(*) FROM docling_load_queue q WHERE q.voyage_key = %s", params)
        else:
            cur.execute("SELECT COUNT(*) FROM docling_load_queue")
        row = cur.fetchone()
        total = row[0] if row else 0
        if voyage:
            cur.execute(
                "SELECT q.file_type, COUNT(*) FROM docling_load_queue q "
                "WHERE q.voyage_key = %s GROUP BY q.file_type ORDER BY 2 DESC",
                params,
            )
        else:
            cur.execute(
                "SELECT q.file_type, COUNT(*) FROM docling_load_queue q "
                "GROUP BY q.file_type ORDER BY 2 DESC"
            )
        by_type = dict(cur.fetchall())
    return {"total": total, "by_type": by_type}
