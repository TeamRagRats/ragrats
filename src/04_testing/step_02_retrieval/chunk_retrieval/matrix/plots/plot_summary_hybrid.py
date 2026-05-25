"""
Plot recall-vs-k for the summary+hybrid sweep (summary_hybrid_test.py).

Aggregates the per-category rows (fact_single / summary / reasoning;
unanswerable is excluded at run time) into an overall recall per top_k, and
draws one line per reformulate/rerank combination — left panel thread recall,
right panel email recall.

Dimensions are read from the flags JSONB (top_k / reformulator / reranker), so
this works regardless of whether the legacy per-knob columns still exist. Pass
--sweep-id to pin one exact run; otherwise the most recent matching row per
(top_k, reformulate, rerank, category) is used.

Run on SPARK (needs postgres):
    cd src/04_testing/step_02_retrieval/chunk_retrieval/matrix
    python plots/plot_summary_hybrid.py --sweep-id <uuid>
    python plots/plot_summary_hybrid.py --out plots/summary_hybrid.png
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[6]))

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.db import connect

CATEGORIES = ("fact_single", "summary", "reasoning")

# (reformulate, rerank) -> line label, drawn in this order.
COMBOS = [
    ((False, False), "base"),
    ((True, False), "+reformulate"),
    ((False, True), "+rerank"),
    ((True, True), "+both"),
]

QUERY = """
    SELECT DISTINCT ON (top_k, reformulate, rerank, question_type)
           (flags->>'top_k')::int                            AS top_k,
           COALESCE((flags->>'reformulator')::bool, false)   AS reformulate,
           COALESCE((flags->>'reranker')::bool, false)       AS rerank,
           question_type, total, thread_hits, email_hits
    FROM test_retrieval_run_logging
    WHERE test_type = 'chunk_retrieval'
      AND flags->>'hybrid' = 'hybrid'
      AND flags->'strategy' ? 'summary'
      AND question_type = ANY(%(cats)s)
      AND (%(sweep_id)s::text IS NULL OR flags->>'sweep_id' = %(sweep_id)s::text)
    ORDER BY top_k, reformulate, rerank, question_type, run_at DESC
"""


def load_curves(sweep_id: str | None) -> dict[tuple[bool, bool], dict[str, list]]:
    """{(reformulate, rerank): {'k', 'thread', 'email'}}, recall summed over categories."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(QUERY, {"cats": list(CATEGORIES), "sweep_id": sweep_id})
        rows = cur.fetchall()

    # (combo, top_k) -> [total, thread_hits, email_hits] summed across categories.
    agg: dict[tuple[tuple[bool, bool], int], list[int]] = {}
    for top_k, reformulate, rerank, _qt, total, thread_hits, email_hits in rows:
        acc = agg.setdefault(((reformulate, rerank), top_k), [0, 0, 0])
        acc[0] += total
        acc[1] += thread_hits
        acc[2] += email_hits or 0

    curves: dict[tuple[bool, bool], dict[str, list]] = {}
    for (combo, top_k), (total, t_hits, e_hits) in agg.items():
        c = curves.setdefault(combo, {"k": [], "thread": [], "email": []})
        c["k"].append(top_k)
        c["thread"].append(t_hits / total if total else 0.0)
        c["email"].append(e_hits / total if total else 0.0)

    for c in curves.values():
        order = sorted(range(len(c["k"])), key=lambda i: c["k"][i])
        c["k"] = [0] + [c["k"][i] for i in order]
        c["thread"] = [0.0] + [c["thread"][i] for i in order]
        c["email"] = [0.0] + [c["email"][i] for i in order]
    return curves


def plot(curves: dict[tuple[bool, bool], dict[str, list]], out: Path) -> None:
    fig, (ax_thread, ax_email) = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    for combo, label in COMBOS:
        if combo not in curves:
            continue
        c = curves[combo]
        ax_thread.plot(c["k"], c["thread"], marker="o", label=label)
        ax_email.plot(c["k"], c["email"], marker="o", label=label)

    for ax, title in ((ax_thread, "Thread recall"), (ax_email, "Email recall")):
        ax.set_title(f"{title} vs top-k")
        ax.set_xlabel("top-k")
        ax.set_xlim(left=0)
        ax.set_ylim(0, 1)
        ax.grid(True, alpha=0.3)
        ax.legend(title="config")
    ax_thread.set_ylabel("recall")

    fig.suptitle("Chunk retrieval recall (summary + hybrid, excl. unanswerable)")
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")


def main() -> None:
    p = argparse.ArgumentParser(description="Plot recall-vs-k for the summary+hybrid sweep")
    p.add_argument("--sweep-id", default=None,
                   help="Pin one sweep by its sweep_id (default: most recent matching rows)")
    p.add_argument("--out", type=Path,
                   default=Path(__file__).resolve().parent / "summary_hybrid.png",
                   help="Output PNG path (default: ./summary_hybrid.png)")
    args = p.parse_args()

    curves = load_curves(args.sweep_id)
    if not curves:
        raise SystemExit(
            "No matching rows (summary + hybrid). "
            "Run summary_hybrid_test.py first, or check --sweep-id."
        )
    for (reformulate, rerank), label in COMBOS:
        c = curves.get((reformulate, rerank))
        if c:
            print(f"{label}: {len(c['k']) - 1} points (k {c['k'][1]}..{c['k'][-1]})")
    plot(curves, args.out)


if __name__ == "__main__":
    main()
