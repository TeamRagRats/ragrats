from __future__ import annotations

# DB-backed run and step lifecycle tracking. Writes rows to runs_logging and step_logging tables.
# start_run/finish_run bracket a full pipeline run; the step() context manager times individual steps.
# Used by run_ingest.py, run_summaries.py, and step_09_summaries (email_summaries, voyage_summaries).

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator
from uuid import UUID, uuid4

import psycopg


def start_run(conn: psycopg.Connection) -> UUID:
    run_id = uuid4()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO runs_logging (run_id, started_at, status) VALUES (%s, %s, 'running')",
            (str(run_id), datetime.now(timezone.utc)),
        )
    conn.commit()
    return run_id


def finish_run(conn: psycopg.Connection, run_id: UUID, status: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE runs_logging SET finished_at = %s, status = %s WHERE run_id = %s",
            (datetime.now(timezone.utc), status, str(run_id)),
        )
    conn.commit()


class StepTimer:
    def __init__(self, conn: psycopg.Connection, run_id: UUID, step_name: str):
        self.conn = conn
        self.run_id = run_id
        self.step_name = step_name
        self.rows_in = 0
        self.rows_out = 0
        self.errors = 0
        self.notes: str | None = None
        self._started: datetime | None = None
        self._row_id: int | None = None

    def __enter__(self) -> "StepTimer":
        self._started = datetime.now(timezone.utc)
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO step_logging (run_id, step_name, started_at) "
                "VALUES (%s, %s, %s) RETURNING id",
                (str(self.run_id), self.step_name, self._started),
            )
            self._row_id = cur.fetchone()[0]
        self.conn.commit()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        finished = datetime.now(timezone.utc)
        started = self._started or finished
        duration_ms = int((finished - started).total_seconds() * 1000)
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE step_logging SET finished_at=%s, duration_ms=%s, "
                "rows_in=%s, rows_out=%s, errors=%s, notes=%s WHERE id=%s",
                (
                    finished,
                    duration_ms,
                    self.rows_in,
                    self.rows_out,
                    self.errors,
                    self.notes,
                    self._row_id,
                ),
            )
        self.conn.commit()


@contextmanager
def step(conn: psycopg.Connection, run_id: UUID, name: str) -> Iterator[StepTimer]:
    timer = StepTimer(conn, run_id, name)
    with timer:
        yield timer
