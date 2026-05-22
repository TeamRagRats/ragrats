"""
Recall sweep for the recall-vs-k graph.

Sweeps run_test.py over top_k = 5, 10, ..., 100 (step 5) for each of the four
embedding strategies, in plain vector mode only — no hybrid, no rerank, no
reformulate. This isolates the embedding strategy so the resulting curve is a
clean recall-vs-k comparison across strategies.

    strategies : plain | late | context | summary   (4)
    top_k      : 5, 10, ..., 100                     (20)
                                              total = 80 runs

ef_search is pinned high (default 200) for every k so the HNSW approximation
does not depress recall at small k — the curve then reflects true retrieval
recall, not ANN noise. (ef_search must be >= top_k; 200 covers k up to 100.)

Each run logs a question_type='total' row to test_retrieval_run_logging with
its top_k, strategy, ef and recall — plot_recall.py reads those rows.

This is a multi-hour job; run it yourself rather than backgrounding:

    cd src/04_testing/step_02_retrieval/chunk_retrieval/matrix
    python recall_i5_test.py

Preview the plan without running anything:

    python recall_i5_test.py --dry-run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

STRATEGIES = ["plain", "late", "context", "summary"]
RUN_TEST = Path(__file__).resolve().parent.parent / "run_test.py"


def build_runs(top_ks: list[int], ef_search: int) -> list[tuple[str, list[str]]]:
    """(label, run_test args) for every strategy x top_k, vector-only."""
    runs: list[tuple[str, list[str]]] = []
    for strategy in STRATEGIES:
        for top_k in top_ks:
            runs.append((
                f"strategy={strategy} top_k={top_k} ef_search={ef_search}",
                ["--strategy", strategy, "--top-k", str(top_k),
                 "--ef-search", str(ef_search)],
            ))
    return runs


def main() -> None:
    p = argparse.ArgumentParser(description="Recall-vs-k sweep (vector-only, per strategy)")
    p.add_argument("--ef-search", type=int, default=200, dest="ef_search", metavar="EF",
                   help="Fixed HNSW ef_search for every k (default: 200; must be >= max top_k)")
    p.add_argument("--max-k", type=int, default=100, dest="max_k", metavar="K",
                   help="Largest top_k to sweep to (default: 100)")
    p.add_argument("--step", type=int, default=5, metavar="S",
                   help="Top-k increment per iteration (default: 5)")
    p.add_argument("--embed-url", default=None,
                   help="Embed server base URL, forwarded to run_test.py")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the run plan and exit without running anything")
    args = p.parse_args()

    top_ks = list(range(args.step, args.max_k + 1, args.step))
    if args.ef_search < max(top_ks):
        p.error(f"--ef-search ({args.ef_search}) must be >= max top_k ({max(top_ks)})")
    passthrough = ["--embed-url", args.embed_url] if args.embed_url else []

    runs = build_runs(top_ks, args.ef_search)
    print(f"Recall sweep: {len(runs)} runs | strategies: {STRATEGIES} "
          f"| top_k: {top_ks} | ef_search: {args.ef_search}")
    for i, (label, _) in enumerate(runs, 1):
        print(f"  {i:>3}. {label}")
    if args.dry_run:
        return

    failures: list[str] = []
    started = time.monotonic()
    for i, (label, run_args) in enumerate(runs, 1):
        print(f"\n=== [{i}/{len(runs)}] {label} ===")
        t0 = time.monotonic()
        result = subprocess.run(
            [sys.executable, str(RUN_TEST), *run_args, *passthrough],
            cwd=str(RUN_TEST.parent),
        )
        dt = time.monotonic() - t0
        if result.returncode != 0:
            print(f"  !! FAILED (exit {result.returncode}) after {dt:.0f}s")
            failures.append(label)
        else:
            print(f"  done in {dt:.0f}s")

    total = time.monotonic() - started
    print(f"\nRecall sweep complete: {len(runs) - len(failures)}/{len(runs)} ok "
          f"in {total/60:.1f} min")
    if failures:
        print("Failed runs:")
        for label in failures:
            print(f"  - {label}")
        sys.exit(1)


if __name__ == "__main__":
    main()
