"""Populate ground_truth.question_reformulated once, up front.

Reformulates every ground-truth question via the same reformulate_query the
retrieval pipeline uses and writes the result back to the DB, so the retrieval
sweeps can read it instead of re-running reformulation on every run (which is
slow and lost on a crash). Each row is committed as it is written, so an
interrupted run keeps its progress and a re-run resumes where it stopped.

Needs postgres + the LLM server (8002). Run from anywhere:

    python src/02_retrieval/step_00_query_reformulation/populate_ground_truth.py
    python src/02_retrieval/step_00_query_reformulation/populate_ground_truth.py --force
    python src/02_retrieval/step_00_query_reformulation/populate_ground_truth.py --dry-run

By default only rows with a NULL question_reformulated are filled; --force
recomputes every row (e.g. after the reformulation prompt changes).
"""
from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _repo_root = _here.parents[2]
    _retrieval = _here.parent
    for _p in (_repo_root, _retrieval):
        sys.path.insert(0, str(_p))

import argparse

from core.db import connect
from clients.llm_client import LLMClient, DEFAULT_BASE_URL
from step_00_query_reformulation import reformulate_query


def _load_targets(conn, force: bool) -> list[tuple[str, str]]:
    """(question_id, question) rows that still need a reformulation."""
    where = "" if force else "WHERE question_reformulated IS NULL"
    rows = conn.execute(f"""
        SELECT question_id::text, question
        FROM ground_truth
        {where}
        ORDER BY question_id::text
    """).fetchall()
    return [(qid, q) for qid, q in rows]


def main() -> None:
    p = argparse.ArgumentParser(description="Populate ground_truth.question_reformulated")
    p.add_argument("--llm-url", default=DEFAULT_BASE_URL, help="LLM server base URL")
    p.add_argument("--force", action="store_true",
                   help="Recompute every row, not just the NULL ones")
    p.add_argument("--dry-run", action="store_true",
                   help="Print how many rows would be reformulated and exit")
    args = p.parse_args()

    with connect() as conn:
        targets = _load_targets(conn, args.force)
        scope = "all" if args.force else "missing"
        print(f"ground_truth rows to reformulate ({scope}): {len(targets)}")
        if args.dry_run or not targets:
            return

        llm = LLMClient(base_url=args.llm_url)
        for i, (question_id, question) in enumerate(targets, 1):
            reformulated = reformulate_query(llm, question)
            conn.execute(
                "UPDATE ground_truth SET question_reformulated = %s WHERE question_id = %s",
                (reformulated, question_id),
            )
            conn.commit()
            print(f"  [{i}/{len(targets)}] {question_id}")

    print(f"Done: {len(targets)} rows reformulated.")


if __name__ == "__main__":
    main()
