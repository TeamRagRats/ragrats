from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import psycopg


@dataclass
class VoyageSummary:
    voyage_key: str
    n_emails: int
    n_threads: int
    n_attachments: int
    n_bytes: int
    n_errors: int
    wall_time_ms: int


def _fmt_mb(n_bytes: int) -> str:
    return f"{n_bytes / (1024 * 1024):.1f} MB"


def _fmt_secs(ms: int) -> str:
    return f"{ms / 1000:.1f}s"


def format_per_voyage_line(s: VoyageSummary) -> str:
    return (
        f"[{s.voyage_key}] {s.n_emails} emails "
        f"· {s.n_threads} threads "
        f"· {s.n_attachments} attachments "
        f"· {_fmt_mb(s.n_bytes)} "
        f"· {_fmt_secs(s.wall_time_ms)}"
    )


def format_final_table(summaries: Iterable[VoyageSummary]) -> str:
    rows = list(summaries)
    headers = ("voyage_key", "n_emails", "n_threads", "n_attachments", "bytes", "errors", "wall_time")
    data = [
        (
            s.voyage_key,
            str(s.n_emails),
            str(s.n_threads),
            str(s.n_attachments),
            _fmt_mb(s.n_bytes),
            str(s.n_errors),
            _fmt_secs(s.wall_time_ms),
        )
        for s in rows
    ]
    widths = [len(h) for h in headers]
    for row in data:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    sep = "  "
    out_lines = [sep.join(h.ljust(widths[i]) for i, h in enumerate(headers))]
    out_lines.append(sep.join("-" * widths[i] for i in range(len(headers))))
    for row in data:
        out_lines.append(sep.join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
    return "\n".join(out_lines)


def load_latest_summaries(conn: psycopg.Connection) -> list[VoyageSummary]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT voyage_key, n_emails, n_threads, n_attachments, n_bytes, "
            "n_errors, wall_time_ms FROM file_counters "
            "WHERE run_id = (SELECT run_id FROM import_runs ORDER BY started_at DESC LIMIT 1) "
            "ORDER BY voyage_key"
        )
        return [VoyageSummary(*row) for row in cur.fetchall()]


if __name__ == "__main__":
    from ..shared.db import connect

    with connect() as conn:
        summaries = load_latest_summaries(conn)
    print(format_final_table(summaries))
