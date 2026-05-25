"""
Plot recall-vs-k broken down by question category, one plot per strategy.

Same vector-only sweep as plot_recall.py, but instead of the aggregate 'total'
row this reads the per-category rows (fact_single / summary / reasoning) that
run_test.py already logs. The figure is a grid: one row per strategy, two
columns (thread recall, email recall); each subplot draws one line per
question category so you can see where a strategy struggles as k rises.

Run on SPARK (needs postgres):
    cd src/04_testing/step_02_retrieval/chunk_retrieval/matrix
    python plot_recall_by_category.py
    python plot_recall_by_category.py --ef 200 --out recall_by_category.png
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[5]))

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.db import connect

STRATEGIES = ["plain", "late", "context", "summary"]
CATEGORIES = ["fact_single", "summary", "reasoning"]

QUERY = """
    SELECT DISTINCT ON (strategy, question_type, top_k)
           strategy, question_type, top_k, thread_recall, email_recall
    FROM test_retrieval_run_logging
    WHERE test_type = 'chunk_retrieval'
      AND question_type IN ('fact_single', 'summary', 'reasoning')
      AND ef = %s
      AND flags->>'hybrid' IS NULL
      AND COALESCE((flags->>'reranker')::bool, false) = false
      AND COALESCE((flags->>'reformulator')::bool, false) = false
    ORDER BY strategy, question_type, top_k, run_at DESC
"""


def load_curves(ef: int) -> dict[str, dict[str, dict[str, list]]]:
    """{strategy: {category: {'k', 'thread', 'email'}}}, each anchored at k=0."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(QUERY, (ef,))
        rows = cur.fetchall()

    raw: dict[str, dict[str, list[tuple]]] = {}
    for strategy, category, top_k, thread_recall, email_recall in rows:
        raw.setdefault(strategy, {}).setdefault(category, []).append(
            (top_k, float(thread_recall), float(email_recall or 0.0))
        )

    curves: dict[str, dict[str, dict[str, list]]] = {}
    for strategy, by_cat in raw.items():
        curves[strategy] = {}
        for category, pts in by_cat.items():
            pts.sort(key=lambda r: r[0])
            curves[strategy][category] = {
                "k": [0] + [p[0] for p in pts],
                "thread": [0.0] + [p[1] for p in pts],
                "email": [0.0] + [p[2] for p in pts],
            }
    return curves


def _ordered(keys, preferred):
    """Preferred items first (in their order), then any extras seen in data."""
    return [k for k in preferred if k in keys] + [k for k in keys if k not in preferred]


def plot(curves: dict[str, dict[str, dict[str, list]]], ef: int, out: Path) -> None:
    strategies = _ordered(curves.keys(), STRATEGIES)
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
            ax.set_title(f"{strategy} — {metric} recall")
            ax.set_xlim(left=0)
            ax.set_ylim(0, 1)
            ax.grid(True, alpha=0.3)
            ax.legend(title="category", fontsize="small")
            if col == 0:
                ax.set_ylabel("recall")
            if row == len(strategies) - 1:
                ax.set_xlabel("top-k")

    fig.suptitle(f"Chunk retrieval recall by category (vector-only, ef_search={ef})")
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
        cats = ", ".join(f"{c}({len(v['k']) - 1})" for c, v in by_cat.items())
        print(f"{strategy}: {cats}")
    plot(curves, args.ef, args.out)


if __name__ == "__main__":
    main()
