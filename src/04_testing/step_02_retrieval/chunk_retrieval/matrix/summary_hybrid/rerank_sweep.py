"""Rerank config for the summary sweep, without redundant reranker calls.

The reranker score for a (query, chunk) pair does not depend on top_k, so we
rerank each question ONCE on a deep vector pool and then read every top_k off a
prefix slice of that single ordering. This replaces the naive "retrieve 3*k and
re-rerank the whole pool for every k" (one reranker call per k per question)
with one reranker call per question for the entire top_k sweep.
"""
from __future__ import annotations

import uuid

from log.log_testing import log_retrieval_run
from pipeline import retrieve_for_question
from scoring import score_and_log_question
from step_03_rerank import rerank_chunks


def _rerank_once_per_question(
    conn, *, cache, rows_by_category, reranker, strategy, pool,
) -> dict[str, list]:
    """{question_id: full reranked chunk list} — one reranker call per question.

    Retrieves a `pool`-deep vector candidate set per question (reformulate=False
    embedding) and reranks the whole pool, keeping the complete ordering so any
    top_k can be sliced off later."""
    reranked_by_q: dict[str, list] = {}
    for _category, rows in sorted(rows_by_category.items()):
        for question_id, question, expected_key, *_rest in rows:
            chunks = retrieve_for_question(
                conn,
                client=None, llm=None, reranker=None,
                question=question, expected_key=expected_key,
                top_k=pool, rerank_pool=pool,
                hybrid_mode=None, lexical="bm25", rrf_k=60,
                source_types=None, strategies=[strategy], ef_search=pool,
                query_embedding=cache[(False, question_id)],
            )
            reranked_by_q[question_id] = rerank_chunks(
                reranker, question, chunks, top_k=len(chunks),
            )
    return reranked_by_q


def run_rerank_config(
    conn, *, cache, rows_by_category, email_thread_map, attach_email_map,
    reranker, strategy, top_ks, pool, make_flags, cell_offset, n_cells,
) -> int:
    """Score the rerank config across every top_k from a single rerank pass.

    make_flags(top_k, rerank_pool) -> flags dict (logged per row). Returns the
    number of cells run (one per top_k) so the caller can keep its counter."""
    print(f"\n=== rerank config: reranking {sum(len(r) for r in rows_by_category.values())} "
          f"questions once on a pool of {pool} ===")
    reranked_by_q = _rerank_once_per_question(
        conn, cache=cache, rows_by_category=rows_by_category,
        reranker=reranker, strategy=strategy, pool=pool,
    )

    for i, top_k in enumerate(top_ks, 1):
        run_id = str(uuid.uuid4())
        flags = make_flags(top_k, pool)
        results: dict[str, dict] = {}
        for category, rows in sorted(rows_by_category.items()):
            thread_hits = email_hits = 0
            for (question_id, question, _expected_key, expected_source_type,
                 expected_source_id, expected_strategy) in rows:
                prefix = reranked_by_q[question_id][:top_k]
                thread_rank, email_rank = score_and_log_question(
                    conn,
                    run_id=run_id, category=category,
                    question_id=question_id, question=question, chunks=prefix,
                    expected_source_type=expected_source_type,
                    expected_source_id=expected_source_id,
                    expected_strategy=expected_strategy,
                    email_thread_map=email_thread_map,
                    attach_email_map=attach_email_map,
                    flags=flags,
                )
                thread_hits += thread_rank is not None
                email_hits += email_rank is not None
            results[category] = {"total": len(rows), "thread_hits": thread_hits,
                                 "email_hits": email_hits}

        for category, r in results.items():
            total = r["total"]
            log_retrieval_run(
                conn, run_id=run_id, test_type="chunk_retrieval",
                question_type=category, total=total,
                thread_hits=r["thread_hits"],
                thread_recall=r["thread_hits"] / total if total else 0.0,
                email_hits=r["email_hits"],
                email_recall=r["email_hits"] / total if total else 0.0,
                flags=flags,
            )
        summary = " | ".join(
            f"{c}: t {r['thread_hits']}/{r['total']} e {r['email_hits']}/{r['total']}"
            for c, r in sorted(results.items())
        )
        print(f"=== [{cell_offset + i}/{n_cells}] top_k={top_k} config=rerank === {summary}")
    return len(top_ks)
