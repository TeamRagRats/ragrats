"""
Plot generation scores (judge + cosine) vs top-k.

Reads test_generation_run_logging and extracts top_k from
flags->'retrieval_flags'->>'top_k'. For each K the most recent run is used.

Two subplots side by side:
  - Left:  avg LLM-as-judge score (1–5) per category
  - Right: avg cosine similarity per category

Run on SPARK (needs postgres):
    cd src/04_testing/step_03_generation
    python plot_scores.py
    python plot_scores.py --out my_plot.png
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[3]))

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.db import connect

CATEGORIES = ["fact_single", "summary", "reasoning", "unanswerable", "all"]

QUERY = """
    SELECT DISTINCT ON ((flags->'retrieval_flags'->>'top_k')::int, category)
        (flags->'retrieval_flags'->>'top_k')::int AS top_k,
        category,
        avg_judge_score,
        avg_cosine
    FROM test_generation_run_logging
    WHERE flags->'retrieval_flags'->>'top_k' IS NOT NULL
    ORDER BY (flags->'retrieval_flags'->>'top_k')::int, category, run_at DESC
"""


def load_curves() -> dict[str, dict[str, list]]:
    """{category: {'k', 'judge', 'cosine'}}"""
    with connect() as conn:
        rows = conn.execute(QUERY).fetchall()

    raw: dict[str, list[tuple]] = {}
    for top_k, category, avg_judge, avg_cosine in rows:
        raw.setdefault(category, []).append((top_k, float(avg_judge), float(avg_cosine)))

    curves: dict[str, dict[str, list]] = {}
    for category, pts in raw.items():
        pts.sort(key=lambda r: r[0])
        curves[category] = {
            "k":      [p[0] for p in pts],
            "judge":  [p[1] for p in pts],
            "cosine": [p[2] for p in pts],
        }
    return curves


def plot(curves: dict[str, dict[str, list]], out: Path) -> None:
    ordered = [c for c in CATEGORIES if c in curves] + \
              [c for c in curves if c not in CATEGORIES]

    fig, (ax_judge, ax_cosine) = plt.subplots(1, 2, figsize=(14, 5), sharex=True)

    for category in ordered:
        c = curves[category]
        style = {"linewidth": 2.5, "marker": "o"} if category == "all" else {"marker": "o"}
        label = category
        ax_judge.plot(c["k"], c["judge"], label=label, **style)
        ax_cosine.plot(c["k"], c["cosine"], label=label, **style)

    ax_judge.set_title("LLM-as-judge score vs top-k")
    ax_judge.set_ylabel("avg judge score (1–5)")
    ax_judge.set_xlabel("top-k")
    ax_judge.set_ylim(1, 5)
    ax_judge.grid(True, alpha=0.3)
    ax_judge.legend(title="category", fontsize="small")

    ax_cosine.set_title("Cosine similarity vs top-k")
    ax_cosine.set_ylabel("avg cosine similarity")
    ax_cosine.set_xlabel("top-k")
    ax_cosine.set_ylim(0, 1)
    ax_cosine.grid(True, alpha=0.3)
    ax_cosine.legend(title="category", fontsize="small")

    fig.suptitle("Generation quality vs retrieval top-k")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")


def main() -> None:
    p = argparse.ArgumentParser(description="Plot generation scores vs top-k")
    p.add_argument("--out", type=Path,
                   default=Path(__file__).resolve().parent / "generation_scores.png",
                   help="Output PNG path (default: ./generation_scores.png)")
    args = p.parse_args()

    curves = load_curves()
    if not curves:
        raise SystemExit("No rows found in test_generation_run_logging. Run run_test.py first.")

    for cat, c in sorted(curves.items()):
        print(f"{cat}: k={c['k']}")
    plot(curves, args.out)


if __name__ == "__main__":
    main()
