"""Loading voyage-key matrix results from test_retrieval_run_logging.

A matrix run shares one matrix_id (stored in flags). Each (strategy, k) is one
row per question_type (fact_single / summary / reasoning / total). The strategy
lives in flags->'strategy' as a JSON array (e.g. ["plain"]), and the metric is
determined by flags->>'rank_threshold' (NULL = recall@k, N = voting rank<= N).
"""

from __future__ import annotations

from core.db import connect


def latest_matrix_id() -> str | None:
    with connect() as conn:
        row = conn.execute("""
            SELECT flags->>'matrix_id'
            FROM test_retrieval_run_logging
            WHERE test_type = 'voyage_key_retrieval'
              AND flags ? 'matrix_id'
            ORDER BY run_at DESC
            LIMIT 1
        """).fetchone()
    return row[0] if row else None


def metric_label(matrix_id: str) -> str:
    with connect() as conn:
        row = conn.execute("""
            SELECT flags->>'rank_threshold'
            FROM test_retrieval_run_logging
            WHERE test_type = 'voyage_key_retrieval'
              AND flags->>'matrix_id' = %s
            LIMIT 1
        """, (matrix_id,)).fetchone()
    rt = row[0] if row else None
    return f"voting rank<= {rt}" if rt else "recall@k"


def load_total(matrix_id: str) -> dict[str, dict[str, list]]:
    """{strategy: {'k': [...], 'recall': [...]}}, starting at the first k (k=1)."""
    with connect() as conn:
        rows = conn.execute("""
            SELECT flags->'strategy'->>0 AS strategy,
                   (flags->>'top_k')::int AS k,
                   thread_recall
            FROM test_retrieval_run_logging
            WHERE test_type = 'voyage_key_retrieval'
              AND question_type = 'total'
              AND flags->>'matrix_id' = %s
            ORDER BY 1, 2
        """, (matrix_id,)).fetchall()

    by_strategy: dict[str, list[tuple]] = {}
    for strategy, k, recall in rows:
        by_strategy.setdefault(strategy, []).append((k, float(recall)))

    curves: dict[str, dict[str, list]] = {}
    for strategy, pts in by_strategy.items():
        pts.sort(key=lambda r: r[0])
        curves[strategy] = {
            "k": [p[0] for p in pts],
            "recall": [p[1] for p in pts],
        }
    return curves


def load_by_category(matrix_id: str) -> dict[str, dict[str, dict[str, list]]]:
    """{strategy: {category: {'k': [...], 'recall': [...]}}}, starting at the first k (k=1)."""
    with connect() as conn:
        rows = conn.execute("""
            SELECT flags->'strategy'->>0 AS strategy,
                   question_type,
                   (flags->>'top_k')::int AS k,
                   thread_recall
            FROM test_retrieval_run_logging
            WHERE test_type = 'voyage_key_retrieval'
              AND question_type IN ('fact_single', 'summary', 'reasoning')
              AND flags->>'matrix_id' = %s
            ORDER BY 1, 2, 3
        """, (matrix_id,)).fetchall()

    raw: dict[str, dict[str, list[tuple]]] = {}
    for strategy, category, k, recall in rows:
        raw.setdefault(strategy, {}).setdefault(category, []).append((k, float(recall)))

    curves: dict[str, dict[str, dict[str, list]]] = {}
    for strategy, by_cat in raw.items():
        curves[strategy] = {}
        for category, pts in by_cat.items():
            pts.sort(key=lambda r: r[0])
            curves[strategy][category] = {
                "k": [p[0] for p in pts],
                "recall": [p[1] for p in pts],
            }
    return curves
