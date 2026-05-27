"""
Recall-vs-k for the summary strategy: the four configs side by side.

One figure, 2 panels — thread recall (left), email recall (right). Each panel
draws one line per config, with each feature isolated on the vector base:
    base         : vector-only
    hybrid       : vector + lexical (BM25) fused via RRF
    reformulate  : vector + LLM query reformulation
    rerank       : vector + reranker

Recall is summed over the answerable categories. The most recent matching row
per (config, top_k, category) is used. A config with no matching rows is simply
omitted.

Run on SPARK (needs postgres):
    cd src/04_testing/step_02_retrieval/chunk_retrieval/matrix/plots
    python summary_recall_overview/plot.py
    python summary_recall_overview/plot.py --sweep-id <uuid>
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
from recall_data import as_xy, four_configs

ORDER = ["base", "hybrid", "reformulate", "rerank"]
LABELS = {
    "base": "base (vector)",
    "hybrid": "hybrid",
    "reformulate": "reformulator",
    "rerank": "reranker",
}


def plot(configs: dict[str, dict[int, tuple[float, float]]], out: Path) -> None:
    series = [c for c in ORDER if configs.get(c)]
    # Pin both x-limits to the measured k-range so the curves sit flush against
    # both axes (no empty margin before the first / after the last point).
    all_k = [k for name in series for k in configs[name]]
    min_k, max_k = min(all_k), max(all_k)
    fig, (ax_thread, ax_email) = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    for name in series:
        # Drop the synthetic (k=0, 0.0) origin so the curves start at the
        # smallest measured k (k=1).
        tx, ty = as_xy(configs[name], "thread")
        ex, ey = as_xy(configs[name], "email")
        ax_thread.plot(tx[1:], ty[1:], marker="o", label=LABELS[name])
        ax_email.plot(ex[1:], ey[1:], marker="o", label=LABELS[name])

    for ax, ylabel in ((ax_thread, "Hit Rate"), (ax_email, "Recall")):
        ax.set_xlabel("top-k", fontsize=22)
        ax.set_ylabel(ylabel, fontsize=22)
        ax.set_xlim(min_k, max_k)
        ax.set_ylim(0.0, 1.0)
        ax.tick_params(labelsize=14)
        ax.grid(True, alpha=0.3)
        ax.legend(title="config", fontsize=12, title_fontsize=13, loc="lower right")

    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")


def main() -> None:
    p = argparse.ArgumentParser(description="Recall-vs-k for summary: base/hybrid/reformulator/reranker")
    p.add_argument("--sweep-id", default=None,
                   help="Pin one sweep by sweep_id (default: most recent matching rows)")
    p.add_argument("--out", type=Path,
                   default=Path(__file__).resolve().parent / "summary_recall_overview.png",
                   help="Output PNG path (default: ./summary_recall_overview.png)")
    args = p.parse_args()

    with connect() as conn:
        configs = four_configs(conn, args.sweep_id)

    if not configs:
        raise SystemExit("No summary rows. Run the matrix / recall sweep first.")
    for name in ORDER:
        c = configs.get(name)
        print(f"{name}: {len(c)} top_k points" if c else f"{name}: (no data yet)")
    plot(configs, args.out)


if __name__ == "__main__":
    main()
