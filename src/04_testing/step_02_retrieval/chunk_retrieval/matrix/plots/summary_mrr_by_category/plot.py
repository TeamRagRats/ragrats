"""
MRR-vs-k by question category for the summary + hybrid pipeline (our best).

Mirror of plot_by_category.py but for MRR (mean reciprocal rank). One figure,
2 panels (thread / email); each draws one line per answerable category
(fact_single / summary / reasoning) plus a 'total score' line aggregated across
them.

Uses the plain hybrid config (no rerank, no reformulate). Reads per-question
ranks from test_retrieval_chunk_logging; pass --sweep-id to pin one sweep.

Run on SPARK (needs postgres):
    cd src/04_testing/step_02_retrieval/chunk_retrieval/matrix/plots
    python summary_mrr_by_category/plot.py
    python summary_mrr_by_category/plot.py --sweep-id <uuid>
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[7]))
    sys.path.insert(0, str(_Path(__file__).resolve().parent.parent / "_shared"))

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.db import connect
from mrr_data import hybrid_by_category
from recall_data import as_xy

ORDER = ["fact_single", "summary", "reasoning", "overall"]


def plot(curves: dict[str, dict[int, tuple[float, float]]], out: Path) -> None:
    series = [c for c in ORDER if curves.get(c)] + [c for c in curves if c not in ORDER]
    fig, (ax_thread, ax_email) = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    for name in series:
        is_total = name == "overall"
        style = (
            {"linewidth": 1.5, "linestyle": ":", "color": "black"}
            if is_total
            else {"marker": "o"}
        )
        label = "total score" if is_total else name
        tx, ty = as_xy(curves[name], "thread")
        ex, ey = as_xy(curves[name], "email")
        ax_thread.plot(tx, ty, label=label, **style)
        ax_email.plot(ex, ey, label=label, **style)

    for ax, title in ((ax_thread, "Thread MRR"), (ax_email, "Email MRR")):
        ax.set_title(f"{title} vs top-k")
        ax.set_xlabel("top-k")
        ax.set_xlim(left=0)
        ax.set_ylim(0, 1)
        ax.grid(True, alpha=0.3)
        ax.legend(title="category")
    ax_thread.set_ylabel("MRR")

    fig.suptitle("Summary + hybrid: MRR by category")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")


def main() -> None:
    p = argparse.ArgumentParser(description="MRR-vs-k by category for summary + hybrid")
    p.add_argument("--sweep-id", default=None,
                   help="Pin one sweep by sweep_id (default: most recent matching rows)")
    p.add_argument("--out", type=Path,
                   default=Path(__file__).resolve().parent / "summary_mrr_by_category.png",
                   help="Output PNG path (default: ./summary_mrr_by_category.png)")
    args = p.parse_args()

    with connect() as conn:
        curves = hybrid_by_category(conn, args.sweep_id)

    if not curves.get("overall"):
        raise SystemExit("No summary+hybrid rows. Run the sweep first.")
    for name in ORDER:
        c = curves.get(name)
        if c:
            print(f"{name}: {len(c)} top_k points")
    plot(curves, args.out)


if __name__ == "__main__":
    main()
