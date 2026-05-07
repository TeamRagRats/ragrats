"""
Source type combination sweep for chunk retrieval.

Finds which combination of source types gives the best chunk recall.
Embeddings are computed once and reused across all combinations.

Modes:
  greedy (default): iteratively adds the source type that improves
                    weighted recall most. Typically 15-20 evaluations.
  exhaustive:       tests all combinations up to --max-combo-size.

Usage:
    python run_source_sweep.py
    python run_source_sweep.py --mode exhaustive --max-combo-size 3
    python run_source_sweep.py --ground-truth-table ground_truth_v2
    python run_source_sweep.py --top-k 30 --expand-window 3
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _repo_root = _here.parents[3]
    _retrieval = _repo_root / "src" / "02_retrieval"
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_retrieval))
    __package__ = "src.testing.retrieval.chunk"

import argparse
import itertools
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

from core.db import connect
from clients.embed_client import EmbedClient, DEFAULT_BASE_URL
from step_02_chunk_retrieval.retrieve_chunks import retrieve_chunks, RetrievedChunk
from step_02_chunk_retrieval.expand_chunks import expand_chunks
from log.log_testing import log_retrieval_run

_QUERY_INSTRUCTION = "Instruct: Retrieve relevant maritime project documents for the given query\nQuery: "
_ALLOWED_GT_TABLES = {"ground_truth_v2", "ground_truth"}
_REPORTS_DIR = Path(__file__).resolve().parent / "reports"

_CATEGORY_COLORS = {
    "commercial_terms":  "#4C72B0",
    "incident_decision": "#DD8452",
    "logistics_cargo":   "#55A868",
}


@dataclass
class ComboResult:
    label: str
    source_types: list[str] | None  # None = all
    results: dict[str, tuple[int, int, float]]  # category -> (hits, total, mrr)
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def weighted_recall(self) -> float:
        total_hits = sum(h for h, t, _ in self.results.values())
        total_qs = sum(t for _, t, _ in self.results.values())
        return total_hits / total_qs if total_qs else 0.0

    def recall(self, category: str) -> float:
        if category not in self.results:
            return 0.0
        hits, total, _ = self.results[category]
        return hits / total if total else 0.0


def _dedup_chunks(all_chunks: list[list[RetrievedChunk]]) -> list[RetrievedChunk]:
    best: dict[str, RetrievedChunk] = {}
    for chunks in all_chunks:
        for chunk in chunks:
            if chunk.chunk_id not in best or chunk.similarity > best[chunk.chunk_id].similarity:
                best[chunk.chunk_id] = chunk
    return sorted(best.values(), key=lambda c: c.similarity, reverse=True)


def _eval_combination(
    conn,
    embedding_map: dict[str, list[float]],
    gt_rows_by_category: dict[str, list],
    source_types: list[str] | None,
    top_k: int,
    expand_window: int,
) -> dict[str, tuple[int, int, float]]:
    results: dict[str, tuple[int, int, float]] = {}
    for category, rows in gt_rows_by_category.items():
        hits = 0
        mrr_sum = 0.0
        total = len(rows)
        for question_id, question, expected_key, expected_chunk_id in rows:
            embedding = embedding_map[question_id]
            chunks = retrieve_chunks(
                conn, embedding, voyage_keys=[expected_key],
                top_k=top_k, source_types=source_types,
            )
            anchor_chunks = _dedup_chunks([chunks])[:top_k]
            expanded = expand_chunks(conn, anchor_chunks, window=expand_window)

            expanded_ids = {c.chunk_id for c in expanded}
            rank = next((i for i, c in enumerate(anchor_chunks, 1) if c.chunk_id == expected_chunk_id), None)

            if expected_chunk_id in expanded_ids:
                hits += 1
            if rank is not None:
                mrr_sum += 1.0 / rank

        results[category] = (hits, total, mrr_sum / total if total else 0.0)
    return results


def _run_combo(
    label: str,
    source_types: list[str] | None,
    conn,
    embedding_map,
    gt_rows_by_category,
    top_k,
    expand_window,
) -> ComboResult:
    print(f"  evaluating: {label} ...", end=" ", flush=True)
    results = _eval_combination(conn, embedding_map, gt_rows_by_category, source_types, top_k, expand_window)
    combo = ComboResult(label=label, source_types=source_types, results=results)
    print(f"weighted recall: {combo.weighted_recall():.1%}")
    return combo


def _greedy_search(
    all_source_types: list[str],
    conn,
    embedding_map,
    gt_rows_by_category,
    top_k,
    expand_window,
) -> list[ComboResult]:
    evaluated: list[ComboResult] = []

    # Baseline: all
    evaluated.append(_run_combo("all", None, conn, embedding_map, gt_rows_by_category, top_k, expand_window))

    # Step 1: evaluate each individual type
    print("\n[greedy] step 1 — individual types")
    individual: list[ComboResult] = []
    for st in all_source_types:
        combo = _run_combo(st, [st], conn, embedding_map, gt_rows_by_category, top_k, expand_window)
        individual.append(combo)
        evaluated.append(combo)

    # Pick best single
    best = max(individual, key=lambda c: c.weighted_recall())
    current_combo = [best.label]
    current_score = best.weighted_recall()
    remaining = [st for st in all_source_types if st != best.label]

    print(f"\n[greedy] best single: {best.label} ({current_score:.1%})")

    # Step 2: greedy expansion
    step = 2
    while remaining:
        print(f"\n[greedy] step {step} — trying to add to {current_combo}")
        best_addition = None
        best_addition_score = current_score
        best_addition_combo: ComboResult | None = None

        for st in remaining:
            candidate = current_combo + [st]
            label = " + ".join(sorted(candidate))
            combo = _run_combo(label, candidate, conn, embedding_map, gt_rows_by_category, top_k, expand_window)
            evaluated.append(combo)
            if combo.weighted_recall() > best_addition_score:
                best_addition_score = combo.weighted_recall()
                best_addition = st
                best_addition_combo = combo

        if best_addition:
            current_combo.append(best_addition)
            current_score = best_addition_score
            remaining.remove(best_addition)
            print(f"[greedy] added {best_addition!r} → {current_score:.1%}")
        else:
            print(f"[greedy] no improvement found — stopping at {current_combo}")
            break
        step += 1

    return evaluated


def _exhaustive_search(
    all_source_types: list[str],
    max_size: int | None,
    conn,
    embedding_map,
    gt_rows_by_category,
    top_k,
    expand_window,
) -> list[ComboResult]:
    evaluated: list[ComboResult] = []

    evaluated.append(_run_combo("all", None, conn, embedding_map, gt_rows_by_category, top_k, expand_window))

    limit = max_size if max_size else len(all_source_types)
    for size in range(1, limit + 1):
        print(f"\n[exhaustive] size {size}")
        for combo in itertools.combinations(all_source_types, size):
            label = " + ".join(sorted(combo))
            result = _run_combo(label, list(combo), conn, embedding_map, gt_rows_by_category, top_k, expand_window)
            evaluated.append(result)

    return evaluated


def _generate_plot(evaluated: list[ComboResult], best_label: str, output_path: Path) -> None:
    categories = [c for c in _CATEGORY_COLORS if any(c in r.results for r in evaluated)]
    sorted_results = sorted(evaluated, key=lambda r: r.weighted_recall())

    fig, ax = plt.subplots(figsize=(12, max(4, len(sorted_results) * 0.5)))

    bar_height = 0.25
    n_cats = len(categories)
    offsets = [(i - (n_cats - 1) / 2) * bar_height for i in range(n_cats)]

    y_positions = list(range(len(sorted_results)))

    for i, (category, offset) in enumerate(zip(categories, offsets)):
        recalls = [r.recall(category) * 100 for r in sorted_results]
        bars = ax.barh(
            [y + offset for y in y_positions],
            recalls,
            height=bar_height,
            label=category,
            color=_CATEGORY_COLORS[category],
            alpha=0.85,
        )

    ax.set_yticks(y_positions)
    ax.set_yticklabels(
        [("★ " if r.label == best_label else "") + r.label for r in sorted_results],
        fontsize=9,
    )
    ax.set_xlabel("Chunk recall (%)")
    ax.set_xlim(0, 100)
    ax.axvline(x=50, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.legend(loc="lower right")
    ax.set_title("Source type combination sweep — chunk recall by category")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def _generate_report(
    evaluated: list[ComboResult],
    best: ComboResult,
    plot_path: Path | None,
    config: dict,
    timestamp: str,
) -> str:
    categories = sorted({c for r in evaluated for c in r.results})
    sorted_results = sorted(evaluated, key=lambda r: r.weighted_recall(), reverse=True)

    lines = [
        f"# Source Type Sweep Report",
        f"",
        f"**Date:** {timestamp}  ",
        f"**Ground truth table:** `{config['gt_table']}`  ",
        f"**top_k:** {config['top_k']} | **expand_window:** ±{config['expand_window']} | **mode:** {config['mode']}  ",
        f"",
        f"## Best combination",
        f"",
        f"**`{best.label}`** — weighted recall: **{best.weighted_recall():.1%}**",
        f"",
    ]
    for cat in categories:
        h, t, mrr = best.results.get(cat, (0, 0, 0.0))
        lines.append(f"- {cat}: {h}/{t} ({h/t:.1%}) | MRR: {mrr:.4f}")

    lines += ["", "## All results", ""]

    header = "| Combination | " + " | ".join(categories) + " | Weighted avg |"
    sep = "|---|" + "|".join(["---"] * len(categories)) + "|---|"
    lines += [header, sep]

    for r in sorted_results:
        marker = " ★" if r.label == best.label else ""
        cells = []
        for cat in categories:
            h, t, _ = r.results.get(cat, (0, 0, 0.0))
            cells.append(f"{h/t:.1%}" if t else "—")
        lines.append(f"| `{r.label}`{marker} | " + " | ".join(cells) + f" | **{r.weighted_recall():.1%}** |")

    if plot_path:
        lines += ["", f"## Plot", "", f"![sweep plot]({plot_path.name})"]

    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description="Source type combination sweep")
    p.add_argument("--mode", choices=["greedy", "exhaustive"], default="greedy")
    p.add_argument("--max-combo-size", type=int, default=None, dest="max_combo_size",
                   help="Max combination size for exhaustive mode (default: all)")
    p.add_argument("--ground-truth-table", default="ground_truth_v2", dest="gt_table")
    p.add_argument("--top-k", type=int, default=20, dest="top_k")
    p.add_argument("--expand-window", type=int, default=2, dest="expand_window")
    p.add_argument("--embed-url", default=DEFAULT_BASE_URL, dest="embed_url")
    args = p.parse_args()

    if args.gt_table not in _ALLOWED_GT_TABLES:
        raise ValueError(f"Unknown ground truth table: {args.gt_table!r}. Allowed: {_ALLOWED_GT_TABLES}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _REPORTS_DIR.mkdir(exist_ok=True)

    with connect() as conn:
        # Fetch distinct source types from chunks
        all_source_types: list[str] = [
            row[0] for row in conn.execute(
                "SELECT DISTINCT source_type FROM chunks ORDER BY source_type"
            ).fetchall()
        ]

        # Fetch ground truth rows
        all_rows = conn.execute(f"""
            SELECT question_id, question, voyage_key, source_chunk_id::text, category
            FROM {args.gt_table}
            ORDER BY category, question_id
        """).fetchall()

    gt_rows_by_category: dict[str, list] = {}
    for question_id, question, voyage_key, source_chunk_id, category in all_rows:
        gt_rows_by_category.setdefault(category, []).append(
            (question_id, question, voyage_key, source_chunk_id)
        )

    total_questions = sum(len(v) for v in gt_rows_by_category.values())
    print(f"Ground truth: {total_questions} questions across {len(gt_rows_by_category)} categories")
    print(f"Source types in chunks: {all_source_types}")
    print(f"Mode: {args.mode} | top_k: {args.top_k} | expand: ±{args.expand_window}")

    # Pre-compute all embeddings once
    print(f"\nPre-computing {total_questions} embeddings ...")
    client = EmbedClient(base_url=args.embed_url)
    all_question_rows = [(q_id, q, key, chunk_id) for rows in gt_rows_by_category.values() for q_id, q, key, chunk_id in rows]
    texts = [_QUERY_INSTRUCTION + q for _, q, _, _ in all_question_rows]
    embeddings = client.embed(texts)
    embedding_map = {q_id: emb for (q_id, _, _, _), emb in zip(all_question_rows, embeddings)}
    print(f"Done.\n")

    with connect() as conn:
        if args.mode == "greedy":
            evaluated = _greedy_search(all_source_types, conn, embedding_map, gt_rows_by_category, args.top_k, args.expand_window)
        else:
            evaluated = _exhaustive_search(all_source_types, args.max_combo_size, conn, embedding_map, gt_rows_by_category, args.top_k, args.expand_window)

        # Log all runs to DB
        for combo in evaluated:
            for category, (hits, total, _) in combo.results.items():
                recall = hits / total if total else 0.0
                log_retrieval_run(
                    conn,
                    run_id=combo.run_id,
                    test_type=f"source_sweep_{args.mode}",
                    question_type=category,
                    top_k=args.top_k,
                    total=total,
                    hits=hits,
                    recall=recall,
                    source_types=combo.source_types or ["all"],
                )

    best = max(evaluated, key=lambda r: r.weighted_recall())

    # Generate plot
    plot_path: Path | None = None
    if HAS_MATPLOTLIB:
        plot_path = _REPORTS_DIR / f"source_sweep_{timestamp}.png"
        _generate_plot(evaluated, best.label, plot_path)
        print(f"\nPlot saved: {plot_path}")
    else:
        print("\nmatplotlib not available — skipping plot")

    # Generate report
    report = _generate_report(
        evaluated, best, plot_path,
        config={"gt_table": args.gt_table, "top_k": args.top_k, "expand_window": args.expand_window, "mode": args.mode},
        timestamp=timestamp,
    )
    report_path = _REPORTS_DIR / f"source_sweep_{timestamp}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"Report saved: {report_path}")

    print(f"\n{'='*60}")
    print(f"BEST: {best.label}")
    print(f"Weighted recall: {best.weighted_recall():.1%}")
    categories = sorted({c for r in evaluated for c in r.results})
    for cat in categories:
        h, t, mrr = best.results.get(cat, (0, 0, 0.0))
        print(f"  {cat}: {h}/{t} ({h/t:.1%}) | MRR: {mrr:.4f}")


if __name__ == "__main__":
    main()
