"""
Recall-vs-k for the summary strategy: hybrid / rerank / reformulate side by side.

One figure, 6 panels — top row thread recall, bottom row email recall; the three
columns isolate one feature each:
    hybrid       : vector-only  vs  hybrid
    rerank       : hybrid       vs  hybrid + rerank
    reformulate  : hybrid       vs  hybrid + reformulate

The rerank/reformulate columns need the full sweep (summary_hybrid_test.py with
no --skip flags); the hybrid column also needs the vector-only summary curve
(recall_i5_test.py). Pass --sweep-id to pin one hybrid sweep; otherwise the most
recent matching row per (top_k, config, category) is used.

Run on SPARK (needs postgres):
    cd src/04_testing/step_02_retrieval/chunk_retrieval/matrix
    python plots/plot_summary_hybrid.py
    python plots/plot_summary_hybrid.py --sweep-id <uuid> --out plots/summary_hybrid.png
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[6]))
    sys.path.insert(0, str(_Path(__file__).resolve().parent))

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.db import connect
from recall_data import as_xy, hybrid_aggregated, vector_summary

BASE = (False, False)
RERANK = (False, True)
REFORMULATE = (True, False)


def _draw(ax, baseline, feature, base_label, feat_label, metric, title):
    if baseline:
        bx, by = as_xy(baseline, metric)
        ax.plot(bx, by, marker="o", label=base_label)
    if feature:
        fx, fy = as_xy(feature, metric)
        ax.plot(fx, fy, marker="o", label=feat_label)
    ax.set_title(title)
    ax.set_xlim(left=0)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize="small")


def plot(vector, hybrid, out: Path) -> None:
    base = hybrid.get(BASE)
    columns = [
        ("hybrid", vector, base, "vector", "hybrid"),
        ("rerank", base, hybrid.get(RERANK), "hybrid", "hybrid + rerank"),
        ("reformulate", base, hybrid.get(REFORMULATE), "hybrid", "hybrid + reformulate"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(18, 9), sharex=True, sharey=True)
    for row, metric in enumerate(("thread", "email")):
        for col, (name, baseline, feature, base_label, feat_label) in enumerate(columns):
            _draw(axes[row][col], baseline, feature, base_label, feat_label,
                  metric, f"{metric} — {name}")
            if col == 0:
                axes[row][col].set_ylabel("recall")
            if row == 1:
                axes[row][col].set_xlabel("top-k")

    fig.suptitle("Summary strategy: recall-vs-k (excl. unanswerable)")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")


def main() -> None:
    p = argparse.ArgumentParser(description="Recall-vs-k for summary: hybrid/rerank/reformulate")
    p.add_argument("--sweep-id", default=None,
                   help="Pin one hybrid sweep by sweep_id (default: most recent matching rows)")
    p.add_argument("--out", type=Path,
                   default=Path(__file__).resolve().parent / "summary_hybrid.png",
                   help="Output PNG path (default: ./summary_hybrid.png)")
    args = p.parse_args()

    with connect() as conn:
        vector = vector_summary(conn)
        hybrid = hybrid_aggregated(conn, args.sweep_id)

    if not hybrid:
        raise SystemExit("No summary+hybrid rows. Run summary_hybrid_test.py first.")
    for combo, name in ((BASE, "hybrid"), (RERANK, "+rerank"), (REFORMULATE, "+reformulate")):
        c = hybrid.get(combo)
        print(f"{name}: {len(c)} top_k points" if c else f"{name}: (no data yet)")
    print(f"vector baseline: {len(vector)} top_k points" if vector else "vector baseline: (none)")
    plot(vector, hybrid, args.out)


if __name__ == "__main__":
    main()
