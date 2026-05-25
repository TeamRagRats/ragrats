"""Shared DB queries for the summary MRR plots.

MRR is computed from the per-question ranks in test_retrieval_chunk_logging
(thread_rank / email_rank; NULL = miss -> reciprocal 0), averaged over the
answerable categories (fact_single + summary + reasoning). The run dimensions
(top_k / hybrid / reformulator / reranker / strategy) live in the flags JSONB.

To avoid mixing re-runs, we first pick the most-recent run_id per
(config, top_k) from test_retrieval_run_logging, then average the ranks of just
those runs' question rows. Pass sweep_id to pin one sweep.
"""
from __future__ import annotations

CATEGORIES = ("fact_single", "summary", "reasoning")

# (hybrid, reformulate, rerank) -> config name, mirroring recall_data.CONFIG_KEYS.
CONFIG_KEYS = {
    "base":        (False, False, False),
    "hybrid":      (True,  False, False),
    "reformulate": (False, True,  False),
    "rerank":      (False, False, True),
}

_LATEST_RUNS = """
    SELECT DISTINCT ON (hybrid, reformulate, rerank, top_k)
           run_id, top_k, hybrid, reformulate, rerank
    FROM (
        SELECT run_id,
               (flags->>'top_k')::int                            AS top_k,
               COALESCE(flags->>'hybrid' = 'hybrid', false)      AS hybrid,
               COALESCE((flags->>'reformulator')::bool, false)   AS reformulate,
               COALESCE((flags->>'reranker')::bool, false)       AS rerank,
               run_at
        FROM test_retrieval_run_logging
        WHERE test_type = 'chunk_retrieval'
          AND flags->'strategy' ? 'summary'
          AND (flags->>'hybrid' IS NULL OR flags->>'hybrid' = 'hybrid')
          AND (%(sweep_id)s::text IS NULL OR flags->>'sweep_id' = %(sweep_id)s::text)
    ) s
    ORDER BY hybrid, reformulate, rerank, top_k, run_at DESC
"""

_RANKS = """
    SELECT run_id, category, thread_rank, email_rank
    FROM test_retrieval_chunk_logging
    WHERE run_id = ANY(%(run_ids)s)
      AND category = ANY(%(cats)s)
"""


def _reciprocal(rank: int | None) -> float:
    return 1.0 / rank if rank else 0.0


def _mrr_by_k(acc: dict[int, list[float]]) -> dict[int, tuple[float, float]]:
    """{top_k: [thread_rr_sum, email_rr_sum, n]} -> {top_k: (thread_mrr, email_mrr)}."""
    out: dict[int, tuple[float, float]] = {}
    for top_k, (t_sum, e_sum, n) in acc.items():
        out[top_k] = (t_sum / n if n else 0.0, e_sum / n if n else 0.0)
    return out


def _latest_runs(conn, sweep_id: str | None) -> list[tuple]:
    """[(run_id, top_k, hybrid, reformulate, rerank)] — newest run per config/top_k."""
    with conn.cursor() as cur:
        cur.execute(_LATEST_RUNS, {"sweep_id": sweep_id})
        return cur.fetchall()


def _ranks_for(conn, run_ids: list[str]) -> list[tuple]:
    if not run_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(_RANKS, {"run_ids": run_ids, "cats": list(CATEGORIES)})
        return cur.fetchall()


def four_configs(conn, sweep_id: str | None = None) -> dict[str, dict[int, tuple[float, float]]]:
    """{config: {top_k: (thread_mrr, email_mrr)}} for base / hybrid / reformulate /
    rerank, averaged over the answerable categories. Missing configs are absent."""
    runs = _latest_runs(conn, sweep_id)
    by_dims = {dims: name for name, dims in CONFIG_KEYS.items()}
    run_meta: dict[str, tuple[str, int]] = {}
    for run_id, top_k, hybrid, reformulate, rerank in runs:
        name = by_dims.get((hybrid, reformulate, rerank))
        if name is not None:
            run_meta[run_id] = (name, top_k)

    acc: dict[str, dict[int, list[float]]] = {}
    for run_id, _category, thread_rank, email_rank in _ranks_for(conn, list(run_meta)):
        name, top_k = run_meta[run_id]
        slot = acc.setdefault(name, {}).setdefault(top_k, [0.0, 0.0, 0])
        slot[0] += _reciprocal(thread_rank)
        slot[1] += _reciprocal(email_rank)
        slot[2] += 1
    return {name: _mrr_by_k(per_k) for name, per_k in acc.items()}


def hybrid_by_category(conn, sweep_id: str | None = None) -> dict[str, dict[int, tuple[float, float]]]:
    """{category|'overall': {top_k: (thread_mrr, email_mrr)}} for the plain hybrid
    config (no reformulate, no rerank)."""
    runs = _latest_runs(conn, sweep_id)
    hybrid_runs: dict[str, int] = {
        run_id: top_k
        for run_id, top_k, hybrid, reformulate, rerank in runs
        if hybrid and not reformulate and not rerank
    }

    per_cat: dict[str, dict[int, list[float]]] = {}
    overall: dict[int, list[float]] = {}
    for run_id, category, thread_rank, email_rank in _ranks_for(conn, list(hybrid_runs)):
        top_k = hybrid_runs[run_id]
        slot = per_cat.setdefault(category, {}).setdefault(top_k, [0.0, 0.0, 0])
        o_slot = overall.setdefault(top_k, [0.0, 0.0, 0])
        for s in (slot, o_slot):
            s[0] += _reciprocal(thread_rank)
            s[1] += _reciprocal(email_rank)
            s[2] += 1
    out = {cat: _mrr_by_k(by_k) for cat, by_k in per_cat.items()}
    out["overall"] = _mrr_by_k(overall)
    return out
