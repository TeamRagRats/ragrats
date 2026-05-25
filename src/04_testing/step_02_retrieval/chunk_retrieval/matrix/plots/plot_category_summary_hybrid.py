"""
Recall-vs-k by question category for the summary + hybrid pipeline (our best).

One figure, 2 panels (thread / email); each draws one line per answerable
category (fact_single / summary / reasoning) plus an 'overall' line aggregated
across them. Unanswerable is excluded.

Uses the plain hybrid config (no rerank, no reformulate). Pass --sweep-id to pin
one sweep; otherwise the most recent matching rows are used.

Run on SPARK (needs postgres):
    cd src/04_testing/step_02_retrieval/chunk_retrieval/matrix
    python plots/plot_category_summary_hybrid.py
    python plots/plot_category_summary_hybrid.py --sweep-id <uuid>
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
from recall_data import as_xy, hybrid_by_category

ORDER = ["fact_single", "summary", "reasoning", "overall"]


def plot(curves: dict[str, dict[int, tuple[float, float]]], out: Path) -> None:
    series = [c for c in ORDER if curves.get(c)] + [c for c in curves if c not in ORDER]
    fig, (ax_thread, ax_email) = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    for name in series:
        style = {"linewidth": 3, "color": "black"} if name == "overall" else {"marker": "o"}
        tx, ty = as_xy(curves[name], "thread")
        ex, ey = as_xy(curves[name], "email")
        ax_thread.plot(tx, ty, label=name, **style)
        ax_email.plot(ex, ey, label=name, **style)

    for ax, title in ((ax_thread, "Thread recall"), (ax_email, "Email recall")):
        ax.set_title(f"{title} vs top-k")
        ax.set_xlabel("top-k")
        ax.set_xlim(left=0)
        ax.set_ylim(0, 1)
        ax.grid(True, alpha=0.3)
        ax.legend(title="category")
    ax_thread.set_ylabel("recall")

    fig.suptitle("Summary + hybrid: recall by category (excl. unanswerable)")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")


def main() -> None:
    p = argparse.ArgumentParser(description="Recall-vs-k by category for summary + hybrid")
    p.add_argument("--sweep-id", default=None,
                   help="Pin one sweep by sweep_id (default: most recent matching rows)")
    p.add_argument("--out", type=Path,
                   default=Path(__file__).resolve().parent / "category_summary_hybrid.png",
                   help="Output PNG path (default: ./category_summary_hybrid.png)")
    args = p.parse_args()

    with connect() as conn:
        curves = hybrid_by_category(conn, args.sweep_id, reformulate=False, rerank=False)

    if not curves.get("overall"):
        raise SystemExit("No summary+hybrid rows. Run summary_hybrid_test.py first.")
    for name in ORDER:
        c = curves.get(name)
        if c:
            print(f"{name}: {len(c)} top_k points")
    plot(curves, args.out)


if __name__ == "__main__":
    main()
