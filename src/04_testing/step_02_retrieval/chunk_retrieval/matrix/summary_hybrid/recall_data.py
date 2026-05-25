"""Shared DB queries for the summary+hybrid recall plots.

All dimensions are read from the flags JSONB (top_k / reformulator / reranker /
hybrid / strategy), so these work regardless of whether the legacy per-knob
columns still exist. Recall is aggregated over the answerable categories
(fact_single + summary + reasoning).
"""
from __future__ import annotations

CATEGORIES = ("fact_single", "summary", "reasoning")

_HYBRID_QUERY = """
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

# One row per (config dimensions, top_k, category): every summary-strategy run
# whose retrieval mode is vector or hybrid. Buckets into the four configs in
# Python (see CONFIG_KEYS). Most-recent row per dimension wins.
_CONFIG_QUERY = """
    SELECT DISTINCT ON (hybrid, reformulate, rerank, top_k, question_type)
           (flags->>'top_k')::int                            AS top_k,
           (flags->>'hybrid' = 'hybrid')                     AS hybrid,
           COALESCE((flags->>'reformulator')::bool, false)   AS reformulate,
           COALESCE((flags->>'reranker')::bool, false)       AS rerank,
           question_type, total, thread_hits, email_hits
    FROM test_retrieval_run_logging
    WHERE test_type = 'chunk_retrieval'
      AND flags->'strategy' ? 'summary'
      AND (flags->>'hybrid' IS NULL OR flags->>'hybrid' = 'hybrid')
      AND question_type = ANY(%(cats)s)
      AND (%(sweep_id)s::text IS NULL OR flags->>'sweep_id' = %(sweep_id)s::text)
    ORDER BY hybrid, reformulate, rerank, top_k, question_type, run_at DESC
"""

# Each feature isolated on top of the vector base (one knob at a time).
# (hybrid, reformulate, rerank)
CONFIG_KEYS = {
    "base":        (False, False, False),
    "hybrid":      (True,  False, False),
    "reformulate": (False, True,  False),
    "rerank":      (False, False, True),
}


def _recall_by_k(acc: dict[int, list[int]]) -> dict[int, tuple[float, float]]:
    """{top_k: [total, thread_hits, email_hits]} -> {top_k: (thread_recall, email_recall)}."""
    out: dict[int, tuple[float, float]] = {}
    for top_k, (total, t_hits, e_hits) in acc.items():
        out[top_k] = (t_hits / total if total else 0.0, e_hits / total if total else 0.0)
    return out


def hybrid_by_category(
    conn, sweep_id: str | None, reformulate: bool, rerank: bool,
) -> dict[str, dict[int, tuple[float, float]]]:
    """{category|'overall': {top_k: (thread_recall, email_recall)}} for one hybrid config."""
    with conn.cursor() as cur:
        cur.execute(_HYBRID_QUERY, {"cats": list(CATEGORIES), "sweep_id": sweep_id})
        rows = cur.fetchall()
    per_cat: dict[str, dict[int, list[int]]] = {}
    overall: dict[int, list[int]] = {}
    for top_k, rf, rr, qt, total, t_hits, e_hits in rows:
        if rf != reformulate or rr != rerank:
            continue
        slot = per_cat.setdefault(qt, {}).setdefault(top_k, [0, 0, 0])
        o_slot = overall.setdefault(top_k, [0, 0, 0])
        for s in (slot, o_slot):
            s[0] += total
            s[1] += t_hits
            s[2] += e_hits or 0
    out = {cat: _recall_by_k(by_k) for cat, by_k in per_cat.items()}
    out["overall"] = _recall_by_k(overall)
    return out


def four_configs(conn, sweep_id: str | None = None) -> dict[str, dict[int, tuple[float, float]]]:
    """{config: {top_k: (thread_recall, email_recall)}} for base / hybrid /
    reformulate / rerank — each isolated on the vector base, summed over the
    answerable categories. Missing configs are simply absent from the result.
    Pass sweep_id to pin one sweep; otherwise the most recent matching rows win."""
    with conn.cursor() as cur:
        cur.execute(_CONFIG_QUERY, {"cats": list(CATEGORIES), "sweep_id": sweep_id})
        rows = cur.fetchall()
    by_dims = {dims: name for name, dims in CONFIG_KEYS.items()}
    acc: dict[str, dict[int, list[int]]] = {}
    for top_k, hybrid, reformulate, rerank, _qt, total, t_hits, e_hits in rows:
        name = by_dims.get((hybrid, reformulate, rerank))
        if name is None:
            continue
        slot = acc.setdefault(name, {}).setdefault(top_k, [0, 0, 0])
        slot[0] += total
        slot[1] += t_hits
        slot[2] += e_hits or 0
    return {name: _recall_by_k(per_k) for name, per_k in acc.items()}


def as_xy(curve: dict[int, tuple[float, float]], metric: str) -> tuple[list[int], list[float]]:
    """Sorted (k, recall) for 'thread' or 'email', anchored at the origin (k=0, 0.0)."""
    idx = 0 if metric == "thread" else 1
    ks = sorted(curve)
    return [0] + ks, [0.0] + [curve[k][idx] for k in ks]
