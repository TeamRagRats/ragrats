"""
MRR-vs-k for the summary strategy: the four configs side by side.

Mirror of plot_overview.py but for MRR (mean reciprocal rank) instead of recall.
One figure, 2 panels — thread MRR (left), email MRR (right). Each panel draws
one line per config, with each feature isolated on the vector base:
    base         : vector-only
    hybrid       : vector + BM25 fused via RRF
    reformulate  : vector + LLM query reformulation
    rerank       : vector + reranker

MRR is averaged over the answerable categories. Reads per-question ranks from
test_retrieval_chunk_logging; pass --sweep-id to pin one sweep.

Run on SPARK (needs postgres):
    cd src/04_testing/step_02_retrieval/chunk_retrieval/matrix/plots
    python summary_mrr_overview/plot.py
    python summary_mrr_overview/plot.py --sweep-id <uuid>
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
from mrr_data import four_configs
from recall_data import as_xy

ORDER = ["base", "hybrid", "reformulate", "rerank"]
LABELS = {
    "base": "base (vector)",
    "hybrid": "hybrid",
    "reformulate": "reformulator",
    "rerank": "reranker",
}


def plot(configs: dict[str, dict[int, tuple[float, float]]], out: Path) -> None:
    series = [c for c in ORDER if configs.get(c)]
    fig, (ax_thread, ax_email) = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    for name in series:
        tx, ty = as_xy(configs[name], "thread")
        ex, ey = as_xy(configs[name], "email")
        ax_thread.plot(tx, ty, marker="o", label=LABELS[name])
        ax_email.plot(ex, ey, marker="o", label=LABELS[name])

    for ax, title in ((ax_thread, "Thread MRR"), (ax_email, "Email MRR")):
        ax.set_title(f"{title} vs top-k")
        ax.set_xlabel("top-k")
        ax.set_xlim(left=0)
        ax.set_ylim(0, 1)
        ax.grid(True, alpha=0.3)
        ax.legend(title="config")
    ax_thread.set_ylabel("MRR")

    fig.suptitle("Summary strategy: base / hybrid / reformulator / reranker — MRR")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")


def main() -> None:
    p = argparse.ArgumentParser(description="MRR-vs-k for summary: base/hybrid/reformulator/reranker")
    p.add_argument("--sweep-id", default=None,
                   help="Pin one sweep by sweep_id (default: most recent matching rows)")
    p.add_argument("--out", type=Path,
                   default=Path(__file__).resolve().parent / "summary_mrr_overview.png",
                   help="Output PNG path (default: ./summary_mrr_overview.png)")
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
