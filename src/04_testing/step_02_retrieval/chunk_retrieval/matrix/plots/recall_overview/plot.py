"""
Plot the recall-vs-k curve produced by recall/sweep.py.

Reads the question_type='total' rows from test_retrieval_run_logging for the
vector-only sweep (no hybrid / rerank / reformulate) at the pinned ef_search,
keeps the most recent run per (strategy, top_k), and draws one line per
strategy for both thread and email recall.

Run on SPARK (needs postgres):
    cd src/04_testing/step_02_retrieval/chunk_retrieval/matrix/plots
    python recall_overview/plot.py
    python recall_overview/plot.py --ef 200
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[7]))

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.db import connect

STRATEGIES = ["plain", "late", "context", "summary"]
# Distinct marker per line so the series are legible without relying on colour
# (colour-blind friendly): circle, square, triangle, diamond.
MARKERS = ["o", "s", "^", "D"]

# Dimensions (strategy / top_k / ef_search) live in the flags JSONB, and
# run_test.py logs one row per answerable category — there is no 'total' row.
# These rows carry per-category recall *rates* (thread_recall/email_recall);
# the thread_hits/email_hits count columns are NULL here, so we aggregate the
# rates into a question-count-weighted mean over the categories in Python.
QUERY = """
    SELECT DISTINCT ON (flags->'strategy'->>0, (flags->>'top_k')::int, question_type)
           flags->'strategy'->>0                            AS strategy,
           (flags->>'top_k')::int                           AS top_k,
           question_type, total, thread_recall, email_recall
    FROM test_retrieval_run_logging
    WHERE test_type = 'chunk_retrieval'
      AND question_type IN ('fact_single', 'summary', 'reasoning')
      AND (flags->>'ef_search')::int = %s
      AND flags->>'hybrid' IS NULL
      AND COALESCE((flags->>'reranker')::bool, false) = false
      AND COALESCE((flags->>'reformulator')::bool, false) = false
      AND jsonb_array_length(flags->'strategy') = 1
    ORDER BY flags->'strategy'->>0, (flags->>'top_k')::int, question_type, run_at DESC
"""


def load_curve(ef: int) -> dict[str, dict[str, list]]:
    """{strategy: {'k': [...], 'thread': [...], 'email': [...]}} sorted by k."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(QUERY, (ef,))
        rows = cur.fetchall()

    # strategy -> top_k -> [sum(total), sum(thread_rate*total), sum(email_rate*total)],
    # accumulated over the categories so we can take a question-count-weighted mean.
    acc: dict[str, dict[int, list[float]]] = {}
    for strategy, top_k, _qt, total, thread_recall, email_recall in rows:
        n = total or 0
        slot = acc.setdefault(strategy, {}).setdefault(top_k, [0.0, 0.0, 0.0])
        slot[0] += n
        slot[1] += float(thread_recall or 0.0) * n
        slot[2] += float(email_recall or 0.0) * n

    curves: dict[str, dict[str, list]] = {}
    for strategy, by_k in acc.items():
        ks = sorted(by_k)
        # Curves start at the smallest measured k (k=5); no synthetic origin.
        curves[strategy] = {
            "k": ks,
            "thread": [by_k[k][1] / by_k[k][0] if by_k[k][0] else 0.0 for k in ks],
            "email": [by_k[k][2] / by_k[k][0] if by_k[k][0] else 0.0 for k in ks],
        }
    return curves


def plot(curves: dict[str, dict[str, list]], ef: int, out: Path) -> None:
    order = [s for s in STRATEGIES if s in curves] + [
        s for s in curves if s not in STRATEGIES
    ]
    # Span the x-axis exactly over the measured k-range so the curves sit flush
    # against both spines (no empty gap between the y-axis and the first point).
    min_k = min(c["k"][0] for c in curves.values())
    max_k = max(c["k"][-1] for c in curves.values())

    fig, (ax_thread, ax_email) = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    for ax, metric, ylabel, title in (
        (ax_thread, "thread", "Hit Rate", "Threads"),
        (ax_email, "email", "Recall", "Emails"),
    ):
        for i, strategy in enumerate(order):
            c = curves[strategy]
            ax.plot(c["k"], c[metric], marker=MARKERS[i % len(MARKERS)], label=strategy)
        ax.set_title(title, fontsize=22)
        ax.set_xlabel("Top-k", fontsize=22)
        ax.set_ylabel(ylabel, fontsize=22)
        ax.set_xlim(min_k, max_k)
        ax.set_ylim(0.2, 1.0)
        ax.tick_params(labelsize=14)
        ax.grid(True, alpha=0.3)
        ax.legend(title="strategy", fontsize=12, title_fontsize=13)

    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")


def main() -> None:
    p = argparse.ArgumentParser(description="Plot recall-vs-k from the recall sweep")
    p.add_argument("--ef", type=int, default=200,
                   help="ef_search the sweep was run with (default: 200)")
    p.add_argument("--out", type=Path,
                   default=Path(__file__).resolve().parent / "recall_overview.png",
                   help="Output PNG path (default: ./recall_overview.png)")
    args = p.parse_args()

    curves = load_curve(args.ef)
    if not curves:
        raise SystemExit(
            f"No matching rows (ef={args.ef}, vector-only). "
            "Run recall_i5_test.py first, or check --ef."
        )
    for strategy, c in curves.items():
        print(f"{strategy}: {len(c['k'])} points (k {c['k'][0]}..{c['k'][-1]})")
    plot(curves, args.ef, args.out)


if __name__ == "__main__":
    main()
