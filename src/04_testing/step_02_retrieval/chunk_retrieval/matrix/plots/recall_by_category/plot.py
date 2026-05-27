"""
Plot recall-vs-k broken down by question category, one plot per strategy.

Same vector-only sweep as recall/sweep.py, but instead of the aggregate 'total'
row this reads the per-category rows (fact_single / summary / reasoning) that
run_test.py already logs. The figure is a grid: one row per strategy, two
columns (thread recall, email recall); each subplot draws one line per
question category so you can see where a strategy struggles as k rises.

Run on SPARK (needs postgres):
    cd src/04_testing/step_02_retrieval/chunk_retrieval/matrix/plots
    python recall_by_category/plot.py
    python recall_by_category/plot.py --ef 200
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
CATEGORIES = ["fact_single", "summary", "reasoning"]

# Strategy / top_k / ef_search live in the flags JSONB (no flat columns), so we
# read the per-category recall *rates* straight from thread_recall/email_recall.
QUERY = """
    SELECT DISTINCT ON (flags->'strategy'->>0, question_type, (flags->>'top_k')::int)
           flags->'strategy'->>0                            AS strategy,
           question_type,
           (flags->>'top_k')::int                           AS top_k,
           thread_recall, email_recall
    FROM test_retrieval_run_logging
    WHERE test_type = 'chunk_retrieval'
      AND question_type IN ('fact_single', 'summary', 'reasoning')
      AND (flags->>'ef_search')::int = %s
      AND flags->>'hybrid' IS NULL
      AND COALESCE((flags->>'reranker')::bool, false) = false
      AND COALESCE((flags->>'reformulator')::bool, false) = false
      AND jsonb_array_length(flags->'strategy') = 1
    ORDER BY flags->'strategy'->>0, question_type, (flags->>'top_k')::int, run_at DESC
"""


def load_curves(ef: int) -> dict[str, dict[str, dict[str, list]]]:
    """{strategy: {category: {'k', 'thread', 'email'}}}, starting at the first k."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(QUERY, (ef,))
        rows = cur.fetchall()

    raw: dict[str, dict[str, list[tuple]]] = {}
    for strategy, category, top_k, thread_recall, email_recall in rows:
        raw.setdefault(strategy, {}).setdefault(category, []).append(
            (top_k, float(thread_recall or 0.0), float(email_recall or 0.0))
        )

    curves: dict[str, dict[str, dict[str, list]]] = {}
    for strategy, by_cat in raw.items():
        curves[strategy] = {}
        for category, pts in by_cat.items():
            pts.sort(key=lambda r: r[0])
            # Start each curve at the smallest measured k (no synthetic origin)
            # so the lines sit flush against the y-axis, like the other plots.
            curves[strategy][category] = {
                "k": [p[0] for p in pts],
                "thread": [p[1] for p in pts],
                "email": [p[2] for p in pts],
            }
    return curves


def _ordered(keys, preferred):
    """Preferred items first (in their order), then any extras seen in data."""
    return [k for k in preferred if k in keys] + [k for k in keys if k not in preferred]


def plot(curves: dict[str, dict[str, dict[str, list]]], ef: int, out: Path) -> None:
    strategies = _ordered(curves.keys(), STRATEGIES)
    # Span the x-axis over the measured k-range so the curves sit flush against
    # the y-axis (no empty margin before the first point).
    all_k = [k for by_cat in curves.values() for c in by_cat.values() for k in c["k"]]
    min_k, max_k = min(all_k), max(all_k)
    fig, axes = plt.subplots(
        len(strategies), 2, figsize=(14, 4 * len(strategies)),
        sharex=True, squeeze=False,
    )
    for row, strategy in enumerate(strategies):
        by_cat = curves[strategy]
        categories = _ordered(by_cat.keys(), CATEGORIES)
        for col, metric in enumerate(("thread", "email")):
            ax = axes[row][col]
            for category in categories:
                c = by_cat[category]
                ax.plot(c["k"], c[metric], marker="o", label=category)
            # Column headers only, on the top row: Threads (left) / Emails (right).
            if row == 0:
                ax.set_title("Threads" if col == 0 else "Emails", fontsize=22)
            ax.set_xlim(min_k, max_k)
            ax.set_ylim(0, 1)
            ax.tick_params(labelsize=14)
            ax.grid(True, alpha=0.3)
            ax.legend(title="category", fontsize=12, title_fontsize=13)
            # Hit Rate on every left-column y-axis, Recall on every right one.
            ax.set_ylabel("Hit Rate" if col == 0 else "Recall", fontsize=22)
            if row == len(strategies) - 1:
                ax.set_xlabel("top-k", fontsize=22)

    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")


def main() -> None:
    p = argparse.ArgumentParser(description="Plot recall-vs-k per category, one row per strategy")
    p.add_argument("--ef", type=int, default=200,
                   help="ef_search the sweep was run with (default: 200)")
    p.add_argument("--out", type=Path,
                   default=Path(__file__).resolve().parent / "recall_by_category.png",
                   help="Output PNG path (default: ./recall_by_category.png)")
    args = p.parse_args()

    curves = load_curves(args.ef)
    if not curves:
        raise SystemExit(
            f"No matching rows (ef={args.ef}, vector-only). "
            "Run recall_i5_test.py first, or check --ef."
        )
    for strategy, by_cat in curves.items():
        cats = ", ".join(f"{c}({len(v['k'])})" for c, v in by_cat.items())
        print(f"{strategy}: {cats}")
    plot(curves, args.ef, args.out)


if __name__ == "__main__":
    main()
