"""
Plot the recall-vs-k curve produced by recall_i5_test.py.

Reads the question_type='total' rows from test_retrieval_run_logging for the
vector-only sweep (no hybrid / rerank / reformulate) at the pinned ef_search,
keeps the most recent run per (strategy, top_k), and draws one line per
strategy for both thread and email recall.

Run on SPARK (needs postgres):
    cd src/04_testing/step_02_retrieval/chunk_retrieval/matrix
    python plot_recall.py
    python plot_recall.py --ef 200 --out recall_curve.png
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

QUERY = """
    SELECT DISTINCT ON (strategy, top_k)
           strategy, top_k, thread_recall, email_recall
    FROM test_retrieval_run_logging
    WHERE test_type = 'chunk_retrieval'
      AND question_type = 'total'
      AND ef = %s
      AND flags->>'hybrid' IS NULL
      AND COALESCE((flags->>'reranker')::bool, false) = false
      AND COALESCE((flags->>'reformulator')::bool, false) = false
    ORDER BY strategy, top_k, run_at DESC
"""


def load_curve(ef: int) -> dict[str, dict[str, list]]:
    """{strategy: {'k': [...], 'thread': [...], 'email': [...]}} sorted by k."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(QUERY, (ef,))
        rows = cur.fetchall()

    by_strategy: dict[str, list[tuple]] = {}
    for strategy, top_k, thread_recall, email_recall in rows:
        by_strategy.setdefault(strategy, []).append(
            (top_k, float(thread_recall), float(email_recall or 0.0))
        )

    curves: dict[str, dict[str, list]] = {}
    for strategy, pts in by_strategy.items():
        pts.sort(key=lambda r: r[0])
        curves[strategy] = {
            "k": [p[0] for p in pts],
            "thread": [p[1] for p in pts],
            "email": [p[2] for p in pts],
        }
    return curves


def plot(curves: dict[str, dict[str, list]], ef: int, out: Path) -> None:
    fig, (ax_thread, ax_email) = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    order = [s for s in STRATEGIES if s in curves] + [
        s for s in curves if s not in STRATEGIES
    ]
    for strategy in order:
        c = curves[strategy]
        ax_thread.plot(c["k"], c["thread"], marker="o", label=strategy)
        ax_email.plot(c["k"], c["email"], marker="o", label=strategy)

    for ax, title in ((ax_thread, "Thread recall"), (ax_email, "Email recall")):
        ax.set_title(f"{title} vs top-k")
        ax.set_xlabel("top-k")
        ax.set_ylim(0, 1)
        ax.grid(True, alpha=0.3)
        ax.legend(title="strategy")
    ax_thread.set_ylabel("recall")

    fig.suptitle(f"Chunk retrieval recall (vector-only, ef_search={ef})")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")


def main() -> None:
    p = argparse.ArgumentParser(description="Plot recall-vs-k from the recall sweep")
    p.add_argument("--ef", type=int, default=200,
                   help="ef_search the sweep was run with (default: 200)")
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "recall_curve.png",
                   help="Output PNG path (default: ./recall_curve.png)")
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
