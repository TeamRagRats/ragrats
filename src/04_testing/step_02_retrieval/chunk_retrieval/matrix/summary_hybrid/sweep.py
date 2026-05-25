"""In-process summary+hybrid sweep.

Fixes --strategy summary --hybrid (lexical bm25, rrf_k 60) and sweeps
top_k x reformulate x rerank in a single process. Query embeddings are computed
once up front and cached (see query_cache), so each sweep cell only pays for DB
retrieval (+ optional rerank) — the same idea that made the matrix test fast by
pre-generating all document embeddings.

Run on SPARK where postgres + the embed server (8003) are reachable. The
reformulate dimension reads ground_truth.question_reformulated (run
step_00_query_reformulation/populate_ground_truth.py once first); only the
rerank dimension needs a live server (8004):

    cd src/04_testing/step_02_retrieval/chunk_retrieval/matrix
    python summary_hybrid/sweep.py
    python summary_hybrid/sweep.py --skip-reformulate --skip-rerank
    python summary_hybrid/sweep.py --dry-run
"""
from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _chunk = _here.parents[1]
    _step02_testing = _here.parents[2]
    _repo_root = _here.parents[5]
    _retrieval = _repo_root / "src" / "02_retrieval"
    for _p in (_repo_root, _retrieval, _step02_testing, _chunk, _here):
        sys.path.insert(0, str(_p))

import argparse
import time
import uuid

from core.db import connect
from clients.embed_client import EmbedClient
from clients.rerank_client import RerankClient, DEFAULT_BASE_URL as DEFAULT_RERANK_URL
from clients.embed_client import DEFAULT_BASE_URL as DEFAULT_EMBED_URL
from step_03_rerank import DEFAULT_RERANK_OVERSAMPLE
from log.log_testing import log_retrieval_run

from source_match import load_attachment_email_map, load_email_thread_map
from data import load_ground_truth, load_reformulated
from pipeline import retrieve_for_question
from scoring import score_and_log_question
from query_cache import build_query_embedding_cache

STRATEGY = "summary"
RRF_K = 60
LEXICAL = "bm25"


def _cell_flags(
    top_k: int, reformulate: bool, rerank: bool, rerank_pool: int | None, sweep_id: str,
) -> dict:
    return {
        "top_k": top_k,
        "ef_search": top_k,
        "strategy": [STRATEGY],
        "source_types": "all",
        "hybrid": "hybrid",
        "lexical": LEXICAL,
        "rrf_k": RRF_K,
        "reranker": rerank,
        "rerank_pool": rerank_pool if rerank else None,
        "reformulator": reformulate,
        "sweep_id": sweep_id,
    }


def _run_cell(
    conn, *, run_id, flags, cache, rows_by_category, email_thread_map,
    attach_email_map, reranker, top_k, reformulate, rerank, rerank_pool,
) -> dict[str, dict]:
    results: dict[str, dict] = {}
    cell_reranker = reranker if rerank else None
    for category, rows in sorted(rows_by_category.items()):
        thread_hits = email_hits = 0
        for (question_id, question, expected_key, expected_source_type,
             expected_source_id, expected_strategy) in rows:
            chunks = retrieve_for_question(
                conn,
                client=None, llm=None, reranker=cell_reranker,
                question=question, expected_key=expected_key,
                top_k=top_k, rerank_pool=rerank_pool,
                hybrid_mode="hybrid", lexical=LEXICAL, rrf_k=RRF_K,
                source_types=None, strategies=[STRATEGY], ef_search=None,
                query_embedding=cache[(reformulate, question_id)],
            )
            thread_rank, email_rank = score_and_log_question(
                conn,
                run_id=run_id, category=category,
                question_id=question_id, question=question, chunks=chunks,
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
    return results


def main() -> None:
    p = argparse.ArgumentParser(description="In-process summary+hybrid sweep")
    p.add_argument("--top-k", type=int, action="append", dest="top_ks", metavar="K",
                   help="top-k round (repeatable; default: 5..100 step 5)")
    p.add_argument("--embed-url", default=DEFAULT_EMBED_URL, help="Embed server base URL")
    p.add_argument("--rerank-url", default=DEFAULT_RERANK_URL, help="Reranker server base URL")
    p.add_argument("--skip-reformulate", action="store_true",
                   help="Don't sweep reformulate (off only) — no LLM server needed")
    p.add_argument("--skip-rerank", action="store_true",
                   help="Don't sweep rerank (off only) — no reranker server needed")
    p.add_argument("--dry-run", action="store_true", help="Print the plan and exit")
    args = p.parse_args()

    top_ks = args.top_ks or list(range(5, 101, 5))
    reformulate_opts = [False] if args.skip_reformulate else [False, True]
    rerank_opts = [False] if args.skip_rerank else [False, True]
    n_cells = len(top_ks) * len(reformulate_opts) * len(rerank_opts)
    print(f"summary+hybrid sweep: {n_cells} cells | top_k: {top_ks} "
          f"| reformulate: {reformulate_opts} | rerank: {rerank_opts} "
          f"| lexical={LEXICAL} rrf_k={RRF_K}")
    if args.dry_run:
        return

    client = EmbedClient(base_url=args.embed_url)
    reranker = RerankClient(base_url=args.rerank_url) if True in rerank_opts else None

    with connect() as conn:
        rows_by_category = load_ground_truth(conn)
        reformulated_by_id = load_reformulated(conn) if True in reformulate_opts else {}
        email_thread_map = load_email_thread_map(conn)
        attach_email_map = load_attachment_email_map(conn)

    # Unanswerable has no ground-truth source to retrieve, so recall is
    # undefined for it — exclude it from the sweep (and the plot), matching the
    # voyage-key matrix.
    rows_by_category.pop("unanswerable", None)
    total_qs = sum(len(r) for r in rows_by_category.values())
    counts = " | ".join(f"{c}: {len(r)}" for c, r in sorted(rows_by_category.items()))
    print(f"questions (excl. unanswerable): {total_qs} | {counts}")

    print("Building query-embedding cache ...")
    cache = build_query_embedding_cache(
        client, reformulated_by_id, rows_by_category, reformulate_opts
    )

    sweep_id = str(uuid.uuid4())
    print(f"sweep_id={sweep_id}")
    cell = 0
    started = time.monotonic()
    with connect() as conn:
        for top_k in top_ks:
            for reformulate in reformulate_opts:
                for rerank in rerank_opts:
                    cell += 1
                    rerank_pool = DEFAULT_RERANK_OVERSAMPLE * top_k if rerank else None
                    label = (f"top_k={top_k} reformulate={reformulate} rerank={rerank}")
                    print(f"\n=== [{cell}/{n_cells}] {label} ===")
                    run_id = str(uuid.uuid4())
                    flags = _cell_flags(top_k, reformulate, rerank, rerank_pool, sweep_id)
                    t0 = time.monotonic()
                    results = _run_cell(
                        conn, run_id=run_id, flags=flags, cache=cache,
                        rows_by_category=rows_by_category,
                        email_thread_map=email_thread_map, attach_email_map=attach_email_map,
                        reranker=reranker, top_k=top_k, reformulate=reformulate,
                        rerank=rerank, rerank_pool=rerank_pool,
                    )
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
                    dt = time.monotonic() - t0
                    summary = " | ".join(
                        f"{c}: t {r['thread_hits']}/{r['total']} e {r['email_hits']}/{r['total']}"
                        for c, r in sorted(results.items())
                    )
                    print(f"  done in {dt:.0f}s | {summary}")

    print(f"\nSweep complete: {n_cells} cells in {(time.monotonic()-started)/60:.1f} min"
          f" | sweep_id={sweep_id}")


if __name__ == "__main__":
    main()
