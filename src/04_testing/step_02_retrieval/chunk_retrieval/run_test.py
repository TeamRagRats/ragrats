"""
Isolated chunk retrieval test — step 2 only.

Feeds the correct voyage_key from ground_truth directly to retrieve_chunks,
bypassing step 1 entirely. This measures how well step 2 performs given a
perfect voyage key, making it independent of step 1 errors.

Correctness is source-level, with email being thread-level: emails are
embedded with full thread context, so any email chunk in the same thread as
the expected email counts as a hit. Attachments match on the parent email's
thread regardless of strategy. Chunk-level recall is retired.

Categories: fact_single / summary / reasoning / unanswerable. Results logged
separately per category.

Run on SPARK where both postgres and the embed server are reachable:
    python run_test.py
    python run_test.py --top-k 20
    python run_test.py --strategy late --source-type email
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
import uuid

from core.db import connect
from clients.embed_client import EmbedClient, DEFAULT_BASE_URL
from clients.llm_client import LLMClient
from clients.rerank_client import RerankClient, DEFAULT_BASE_URL as DEFAULT_RERANK_URL
from step_00_query_reformulation import reformulate_query
from step_02_chunk_retrieval import retrieve_chunks, hybrid_retrieve_chunks
from step_03_rerank import rerank_chunks, DEFAULT_RERANK_OVERSAMPLE
from filter_args import resolve_source_types, resolve_strategies
from log.log_chunk_retrieval_testing import log_chunk_retrieval_testing
from log.log_testing import log_retrieval_run
from source_match import (
    load_email_thread_map,
    load_attachment_email_map,
    canonical_thread,
    compute_source_rank,
    serialize_chunks,
)


def _run_for_category(
    conn,
    client: EmbedClient,
    rows: list,
    run_id: str,
    top_k: int,
    category: str,
    source_types: list[str] | None,
    strategies: list[str] | None,
    flags: dict,
    email_thread_map: dict[str, str],
    attach_email_map: dict[str, str],
    llm: LLMClient | None = None,
    hybrid_mode: str | None = None,
    rrf_k: int = 60,
    reranker: RerankClient | None = None,
    rerank_pool: int | None = None,
    ef_search: int | None = None,
) -> tuple[int, int, float]:
    src_hits = 0
    src_mrr_sum = 0.0
    total = len(rows)

    for i, (question_id, question, expected_key, expected_source_type,
            expected_source_id, expected_strategy) in enumerate(rows, 1):
        q = reformulate_query(llm, question) if llm else question
        embedding = client.embed([q])[0]

        step2_top_k = rerank_pool if reranker is not None else top_k
        if hybrid_mode is not None:
            anchor_chunks = hybrid_retrieve_chunks(
                conn, query_text=question, query_embedding=embedding,
                voyage_keys=[expected_key], top_k=step2_top_k,
                source_types=source_types, strategies=strategies,
                rrf_k=rrf_k, mode=hybrid_mode,
                ef_search=ef_search,
            )
        else:
            anchor_chunks = retrieve_chunks(
                conn, embedding, voyage_keys=[expected_key], top_k=step2_top_k,
                source_types=source_types, strategies=strategies,
                ef_search=ef_search,
            )

        if reranker is not None:
            anchor_chunks = rerank_chunks(reranker, question, anchor_chunks, top_k=top_k)

        expected_thread_id = (
            email_thread_map.get(expected_source_id) if expected_source_type == "email" else None
        )
        expected_canonical = canonical_thread(
            expected_source_type, expected_source_id, expected_strategy,
            email_thread_map, attach_email_map,
        )
        src_rank = compute_source_rank(
            anchor_chunks, expected_canonical, email_thread_map, attach_email_map,
        )
        src_hit = src_rank is not None
        if src_hit:
            src_hits += 1
            src_mrr_sum += 1.0 / src_rank

        expected_log = (
            f"email_thread:{expected_thread_id}"
            if expected_source_type == "email"
            else f"{expected_source_type}:{expected_source_id}"
        )
        log_chunk_retrieval_testing(
            conn,
            run_id=run_id,
            question_id=question_id,
            category=category,
            question=question,
            expected_source=expected_log,
            returned_source_ids=[c.source_id for c in anchor_chunks],
            hit=src_hit,
            source_rank=src_rank,
            chunks=serialize_chunks(anchor_chunks),
            flags=flags,
        )

        if i % 50 == 0:
            print(f"  [{category}] {i}/{total} — source recall: {src_hits/i:.1%}")

    src_mrr = src_mrr_sum / total if total else 0.0
    return src_hits, total, src_mrr


def main() -> None:
    p = argparse.ArgumentParser(description="Isolated chunk retrieval test (step 2 only)")
    p.add_argument("--top-k", type=int, default=20, dest="top_k",
                   help="Chunks to retrieve per question (default: 20)")
    p.add_argument("--embed-url", default=DEFAULT_BASE_URL,
                   help=f"Embed server base URL (default: {DEFAULT_BASE_URL})")
    p.add_argument("--source-type", action="append", dest="source_types", metavar="TYPE",
                   help="Filter by source type: email, attachment, all (repeatable; default: email + attachment)")
    p.add_argument("--strategy", action="append", dest="strategies", metavar="STRATEGY",
                   help="Filter by embedding strategy: plain, late, context, summary, all (repeatable; default: plain)")
    p.add_argument("--voyage", type=str, default=None,
                   help="Run only on this voyage_key (default: all voyages in ground_truth)")
    p.add_argument("--reformulate", action="store_true",
                   help="Reformulate questions with LLM before embedding")
    p.add_argument("--hybrid", action="store_true",
                   help="Hybrid retrieval: fuse vector + BM25 via RRF (BM25 against strategy='context' only)")
    p.add_argument("--bm25-only", action="store_true", dest="bm25_only",
                   help="BM25-only retrieval (diagnostic). Implies hybrid retriever path.")
    p.add_argument("--rrf-k", type=int, default=60, dest="rrf_k",
                   help="RRF constant for hybrid fusion (default: 60)")
    p.add_argument("--rerank", action="store_true",
                   help="Rerank retrieved chunks with Qwen3-Reranker-8B")
    p.add_argument("--rerank-pool", type=int, default=None, dest="rerank_pool",
                   help=f"Candidate pool fed to reranker (default: {DEFAULT_RERANK_OVERSAMPLE}x top-k)")
    p.add_argument("--rerank-url", default=DEFAULT_RERANK_URL, dest="rerank_url",
                   help=f"Reranker server base URL (default: {DEFAULT_RERANK_URL})")
    p.add_argument("--ef-search", type=int, default=None, dest="ef_search",
                   help="HNSW ef_search for step 2 (default: = effective LIMIT). "
                        "Must be >= effective LIMIT (= rerank-pool when --rerank, else top-k).")
    args = p.parse_args()

    source_types = resolve_source_types(args.source_types)
    strategies = resolve_strategies(args.strategies)

    voyage_filter_sql = "WHERE voyage_key = %(voyage)s" if args.voyage else ""
    voyage_params = {"voyage": args.voyage} if args.voyage else {}
    with connect() as conn:
        all_rows = conn.execute(f"""
            SELECT question_id::text, question, voyage_key,
                   'email' AS source_type, source_id::text, category,
                   'plain' AS strategy
            FROM ground_truth
            {voyage_filter_sql}
            ORDER BY category, question_id::text
        """, voyage_params).fetchall()

    rows_by_category: dict[str, list] = {}
    for question_id, question, voyage_key, source_type, source_id, category, strategy in all_rows:
        rows_by_category.setdefault(category, []).append(
            (question_id, question, voyage_key, source_type, source_id, strategy)
        )

    summary = " | ".join(f"{cat}: {len(rows)}" for cat, rows in sorted(rows_by_category.items()))
    ef = args.ef_search if args.ef_search is not None else args.top_k
    strategy_str = ",".join(strategies) if strategies else "all"
    print(f"{summary} | top_k: {args.top_k} | ef_search: {ef} | strategy: {strategy_str}")

    client = EmbedClient(base_url=args.embed_url)
    llm = LLMClient() if args.reformulate else None
    hybrid_mode = "bm25_only" if args.bm25_only else ("hybrid" if args.hybrid else None)
    reranker = RerankClient(base_url=args.rerank_url) if args.rerank else None
    rerank_pool = (
        args.rerank_pool
        if args.rerank_pool is not None
        else DEFAULT_RERANK_OVERSAMPLE * args.top_k
    )
    run_id = str(uuid.uuid4())

    flags = {
        "top_k": args.top_k,
        "ef_search": ef,
        "strategy": strategies if strategies is not None else "all",
        "source_types": source_types if source_types is not None else "all",
        "hybrid": hybrid_mode,
        "rrf_k": args.rrf_k if hybrid_mode is not None else None,
        "reranker": reranker is not None,
        "rerank_pool": rerank_pool if reranker is not None else None,
        "reformulator": llm is not None,
    }

    results: dict[str, tuple[int, int, float]] = {}
    with connect() as conn:
        email_thread_map = load_email_thread_map(conn)
        attach_email_map = load_attachment_email_map(conn)
        for category, rows in sorted(rows_by_category.items()):
            src_hits, total, src_mrr = _run_for_category(
                conn, client, rows, run_id, args.top_k, category,
                source_types=source_types, strategies=strategies,
                flags=flags,
                email_thread_map=email_thread_map,
                attach_email_map=attach_email_map,
                llm=llm,
                hybrid_mode=hybrid_mode,
                rrf_k=args.rrf_k,
                reranker=reranker,
                rerank_pool=rerank_pool,
                ef_search=args.ef_search,
            )
            results[category] = (src_hits, total, src_mrr)

    with connect() as conn:
        for category, (src_hits, total, _) in results.items():
            recall = src_hits / total if total else 0.0
            log_retrieval_run(
                conn,
                run_id=run_id,
                test_type="chunk_retrieval",
                question_type=category,
                top_k=args.top_k,
                total=total,
                hits=src_hits,
                recall=recall,
                strategy=strategy_str,
                bm25=hybrid_mode is not None,
                reranker=reranker is not None,
                reformulator=llm is not None,
                ef=ef,
            )

    print(f"\nDone. run_id={run_id} | strategy: {strategy_str}")
    for category, (src_hits, total, src_mrr) in sorted(results.items()):
        src_recall = src_hits / total if total else 0.0
        print(
            f"{category} ({total}): "
            f"source recall: {src_hits}/{total} ({src_recall:.1%}) | MRR: {src_mrr:.4f}"
        )


if __name__ == "__main__":
    main()
