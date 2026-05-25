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
    cd src/04_testing/step_02_retrieval/chunk_retrieval/matrix
    python summary_hybrid/plot_overview.py
    python summary_hybrid/plot_overview.py --out plots_png/summary_hybrid.png
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
    fig, (ax_thread, ax_email) = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    for name in series:
        tx, ty = as_xy(configs[name], "thread")
        ex, ey = as_xy(configs[name], "email")
        ax_thread.plot(tx, ty, marker="o", label=LABELS[name])
        ax_email.plot(ex, ey, marker="o", label=LABELS[name])

    for ax, title in ((ax_thread, "Thread recall"), (ax_email, "Email recall")):
        ax.set_title(f"{title} vs top-k")
        ax.set_xlabel("top-k")
        ax.set_xlim(left=0)
        ax.set_ylim(0, 1)
        ax.grid(True, alpha=0.3)
        ax.legend(title="config")
    ax_thread.set_ylabel("recall")

    fig.suptitle("Summary strategy: base / hybrid / reformulator / reranker")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")


def main() -> None:
    p = argparse.ArgumentParser(description="Recall-vs-k for summary: base/hybrid/reformulator/reranker")
    p.add_argument("--out", type=Path,
                   default=Path(__file__).resolve().parent.parent / "plots_png" / "summary_hybrid.png",
                   help="Output PNG path (default: ../plots_png/summary_hybrid.png)")
    args = p.parse_args()

    with connect() as conn:
        configs = four_configs(conn)

    if not configs:
        raise SystemExit("No summary rows. Run the matrix / recall sweep first.")
    for name in ORDER:
        c = configs.get(name)
        print(f"{name}: {len(c)} top_k points" if c else f"{name}: (no data yet)")
    plot(configs, args.out)


if __name__ == "__main__":
    main()
