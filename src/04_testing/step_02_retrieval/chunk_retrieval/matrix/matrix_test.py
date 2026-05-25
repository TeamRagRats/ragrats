"""
Matrix runner for the chunk retrieval test.

Sweeps run_test.py across every retrieval configuration and lets each run log
its own run_id + flags to test_retrieval_chunk_logging / test_retrieval_run_logging.
Source-type is left at default (email + attachment together).

Dimensions (per top-k round):
    mode         : vector | hybrid | tsrank_only | bm25_only
    lexical      : tsrank | bm25  (swept inside hybrid mode)
    strategy     : plain | late | context | summary
    rrf_k        : swept only for hybrid mode
    reformulate  : off | on   (on requires the LLM server on 8002)
    rerank       : off | on   (on requires the reranker server on 8004)

    vector              : 4 strategies                          =  4
    tsrank_only         : 4 strategies                          =  4
    bm25_only           : 4 strategies                          =  4
    hybrid x lexical    : 4 strategies x 2 lexical x 3 rrf_k    = 24
                                                       subtotal = 36
    x reformulate (2) x rerank (2)                              = 144 runs / top-k round

Run three rounds (top_k = 20, 40, 60) => 432 runs. Each run covers all four
categories. This is a multi-hour job; run it yourself rather than backgrounding:

    cd src/04_testing/step_02_retrieval/chunk_retrieval
    python matrix/matrix_test.py

Drop a dimension to shrink the matrix (and skip the server it needs):

    python matrix/matrix_test.py --skip-reformulate   # no LLM server needed
    python matrix/matrix_test.py --skip-rerank         # no reranker server needed
    python matrix/matrix_test.py --skip-tsrank        # drop the legacy ts_rank lexical variants

Preview the plan without running anything:

    python matrix/matrix_test.py --dry-run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

STRATEGIES = ["plain", "late", "context", "summary"]
RUN_TEST = Path(__file__).resolve().parent.parent / "run_test.py"


def _mode_variants(
    strategy: str, rrf_ks: list[int], include_tsrank: bool,
) -> list[tuple[str, list[str]]]:
    """(mode label, mode args) for one strategy: vector, *_only, hybrid x lexical x rrf_k."""
    strat = ["--strategy", strategy]
    variants: list[tuple[str, list[str]]] = [
        (f"mode=vector strategy={strategy}", strat),
        (f"mode=bm25_only strategy={strategy}", strat + ["--bm25-only"]),
    ]
    if include_tsrank:
        variants.append(
            (f"mode=tsrank_only strategy={strategy}", strat + ["--tsrank-only"])
        )

    lexicals = ["bm25"] + (["tsrank"] if include_tsrank else [])
    for lexical in lexicals:
        for rrf_k in rrf_ks:
            variants.append((
                f"mode=hybrid lexical={lexical} strategy={strategy} rrf_k={rrf_k}",
                strat + ["--hybrid", "--lexical", lexical, "--rrf-k", str(rrf_k)],
            ))
    return variants


def build_runs(
    top_ks: list[int],
    rrf_ks: list[int],
    reformulate_opts: list[bool],
    rerank_opts: list[bool],
    include_tsrank: bool,
) -> list[tuple[str, list[str]]]:
    """Returns (label, run_test args) for every configuration, top-k outer."""
    runs: list[tuple[str, list[str]]] = []
    for top_k in top_ks:
        for reformulate in reformulate_opts:
            for rerank in rerank_opts:
                extra: list[str] = []
                tags = ""
                if reformulate:
                    extra.append("--reformulate")
                    tags += " reformulate"
                if rerank:
                    extra.append("--rerank")
                    tags += " rerank"
                for strategy in STRATEGIES:
                    for mode_label, mode_args in _mode_variants(strategy, rrf_ks, include_tsrank):
                        runs.append((
                            f"top_k={top_k} {mode_label}{tags}",
                            ["--top-k", str(top_k)] + mode_args + extra,
                        ))
    return runs


def main() -> None:
    p = argparse.ArgumentParser(description="Matrix runner for the chunk retrieval test")
    p.add_argument("--top-k", type=int, action="append", dest="top_ks", metavar="K",
                   help="top-k round to run (repeatable; default: 20, 40, 60)")
    p.add_argument("--rrf-k", type=int, action="append", dest="rrf_ks", metavar="R",
                   help="rrf_k value to sweep for hybrid (repeatable; default: 20, 40, 60)")
    p.add_argument("--embed-url", default=None,
                   help="Embed server base URL, forwarded to run_test.py")
    p.add_argument("--skip-reformulate", action="store_true",
                   help="Don't sweep reformulate (off only) — no LLM server needed")
    p.add_argument("--skip-rerank", action="store_true",
                   help="Don't sweep rerank (off only) — no reranker server needed")
    p.add_argument("--skip-tsrank", action="store_true",
                   help="Drop the legacy ts_rank lexical variants (tsrank_only + hybrid lexical=tsrank)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the run plan and exit without running anything")
    args = p.parse_args()

    top_ks = args.top_ks or [20, 40, 60]
    rrf_ks = args.rrf_ks or [20, 40, 60]
    reformulate_opts = [False] if args.skip_reformulate else [False, True]
    rerank_opts = [False] if args.skip_rerank else [False, True]
    include_tsrank = not args.skip_tsrank
    passthrough = ["--embed-url", args.embed_url] if args.embed_url else []

    runs = build_runs(top_ks, rrf_ks, reformulate_opts, rerank_opts, include_tsrank)
    print(f"Matrix: {len(runs)} runs | top_k: {top_ks} | rrf_k (hybrid only): {rrf_ks} "
          f"| reformulate: {reformulate_opts} | rerank: {rerank_opts} "
          f"| tsrank lexical variants: {include_tsrank}")
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
    print(f"\nMatrix complete: {len(runs) - len(failures)}/{len(runs)} ok in {total/60:.1f} min")
    if failures:
        print("Failed runs:")
        for label in failures:
            print(f"  - {label}")
        sys.exit(1)


if __name__ == "__main__":
    main()
