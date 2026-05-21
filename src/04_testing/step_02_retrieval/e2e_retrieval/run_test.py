"""
End-to-end retrieval recall test — full pipeline (step 1 → step 2).

For every ground_truth row, embeds the question, runs the production
pipeline (find_winning_voyage_keys → retrieve_chunks) and checks:
  - voyage key recall : expected_key in winning_keys (vote winners)
  - thread recall     : a retrieved chunk lands in the same email thread as
                        the ground-truth email (loose; the previous "source
                        recall")
  - email  recall     : the retrieved chunk's parent email == ground-truth
                        source_id (strict; email_hit always implies thread_hit)

Categories: fact_single / summary / reasoning / unanswerable. Voyage key and
chunk results are logged separately to test_retrieval_run_logging under the
same run_id; per-question chunk results to test_retrieval_chunk_logging.

Run on SPARK where both postgres and the embed server are reachable:
    python run_test.py
    python run_test.py --top-k-1 500 --top-k-2 20
    python run_test.py --strategy late --source-type email
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _repo_root = _here.parents[3]
    _retrieval = _repo_root / "src" / "02_retrieval"
    _step02_testing = _here.parent
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_retrieval))
    sys.path.insert(0, str(_step02_testing))
    __package__ = "src.testing.retrieval.e2e"

import argparse
import uuid

from core.db import connect
from clients.embed_client import EmbedClient, DEFAULT_BASE_URL
from clients.rerank_client import RerankClient, DEFAULT_BASE_URL as DEFAULT_RERANK_URL
from step_01_voyage_key import find_winning_voyage_keys
from step_02_chunk_retrieval import retrieve_chunks, hybrid_retrieve_chunks
from step_03_rerank import rerank_chunks, DEFAULT_RERANK_OVERSAMPLE
from filter_args import resolve_source_types, resolve_strategies
from log.log_chunk_retrieval_testing import log_chunk_retrieval_testing
from log.log_testing import log_retrieval_run

from source_match import (
    canonical_thread,
    compute_email_rank,
    compute_thread_rank,
    load_attachment_email_map,
    load_email_thread_map,
    serialize_chunks,
)


def _run_for_category(
    conn,
    client: EmbedClient,
    rows: list,
    run_id: str,
    top_k_1: int,
    top_k_2: int,
    category: str,
    source_types: list[str] | None,
    strategies: list[str] | None,
    flags: dict,
    skip_voyage_key: bool,
    email_thread_map: dict[str, str],
    attach_email_map: dict[str, str],
    hybrid_mode: str | None = None,
    rrf_k: int = 60,
    reranker: RerankClient | None = None,
    rerank_pool: int | None = None,
    ef_search_1: int | None = None,
    ef_search_2: int | None = None,
) -> dict:
    key_hits = 0
    thread_hits = 0
    thread_mrr_sum = 0.0
    email_hits = 0
    email_mrr_sum = 0.0
    total = len(rows)

    for i, (question_id, question, expected_key, expected_source_type,
            expected_source_id, expected_strategy) in enumerate(rows, 1):
        embedding = client.embed([question])[0]

        if skip_voyage_key:
            winning_keys, vote_counts = [], {}
        else:
            winning_keys, vote_counts = find_winning_voyage_keys(
                conn, embedding, top_k=top_k_1,
                source_types=source_types, strategies=strategies,
                ef_search=ef_search_1,
            )
            if expected_key in vote_counts:
                key_hits += 1

        step2_top_k = rerank_pool if reranker is not None else top_k_2
        if hybrid_mode is not None:
            anchor_chunks = hybrid_retrieve_chunks(
                conn, query_text=question, query_embedding=embedding,
                voyage_keys=winning_keys if winning_keys else None,
                top_k=step2_top_k,
                source_types=source_types, strategies=strategies,
                rrf_k=rrf_k, mode=hybrid_mode,
                ef_search=ef_search_2,
            )
        else:
            anchor_chunks = retrieve_chunks(
                conn, embedding,
                voyage_keys=winning_keys if winning_keys else None,
                top_k=step2_top_k,
                source_types=source_types, strategies=strategies,
                ef_search=ef_search_2,
            )

        if reranker is not None:
            anchor_chunks = rerank_chunks(reranker, question, anchor_chunks, top_k=top_k_2)

        expected_email_id = expected_source_id if expected_source_type == "email" else None
        expected_thread_id = (
            email_thread_map.get(expected_source_id) if expected_source_type == "email" else None
        )
        expected_canonical = canonical_thread(
            expected_source_type, expected_source_id, expected_strategy,
            email_thread_map, attach_email_map,
        )
        thread_rank = compute_thread_rank(
            anchor_chunks, expected_canonical, email_thread_map, attach_email_map,
        )
        email_rank = compute_email_rank(anchor_chunks, expected_email_id, attach_email_map)
        thread_hit = thread_rank is not None
        email_hit = email_rank is not None
        if thread_hit:
            thread_hits += 1
            thread_mrr_sum += 1.0 / thread_rank
        if email_hit:
            email_hits += 1
            email_mrr_sum += 1.0 / email_rank

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
            thread_hit=thread_hit,
            thread_rank=thread_rank,
            email_hit=email_hit,
            email_rank=email_rank,
            chunks=serialize_chunks(anchor_chunks),
            flags=flags,
        )

        if i % 50 == 0:
            print(
                f"  [{category}] {i}/{total} — "
                f"key: {key_hits/i:.1%} | thread: {thread_hits/i:.1%} | email: {email_hits/i:.1%}"
            )

    thread_mrr = thread_mrr_sum / total if total else 0.0
    email_mrr = email_mrr_sum / total if total else 0.0
    return {
        "total": total,
        "key_hits": key_hits,
        "thread_hits": thread_hits,
        "thread_mrr": thread_mrr,
        "email_hits": email_hits,
        "email_mrr": email_mrr,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="End-to-end retrieval recall test")
    p.add_argument("--top-k-1", type=int, default=500, dest="top_k_1",
                   help="Candidates for voyage_key voting (default: 500)")
    p.add_argument("--top-k-2", type=int, default=20, dest="top_k_2",
                   help="Chunks to retrieve per question (default: 20)")
    p.add_argument("--embed-url", default=DEFAULT_BASE_URL,
                   help=f"Embed server base URL (default: {DEFAULT_BASE_URL})")
    p.add_argument("--source-type", action="append", dest="source_types", metavar="TYPE",
                   help="Filter by source type: email, attachment, all (repeatable; default: email + attachment)")
    p.add_argument("--strategy", action="append", dest="strategies", metavar="STRATEGY",
                   help="Filter by embedding strategy: plain, late, context, summary, all (repeatable; default: late)")
    p.add_argument("--no-voyage-key", action="store_true", dest="no_voyage_key",
                   help="Skip step 1 (voyage_key voting); retrieve chunks across the whole index")
    p.add_argument("--voyage", type=str, default=None,
                   help="Run only on this voyage_key (default: all voyages in ground_truth)")
    p.add_argument("--hybrid", action="store_true",
                   help="Hybrid step 2: fuse vector + BM25 via RRF (BM25 against strategy='context' only)")
    p.add_argument("--bm25-only", action="store_true", dest="bm25_only",
                   help="Step 2 uses BM25 only (diagnostic). Implies hybrid retriever path.")
    p.add_argument("--rrf-k", type=int, default=60, dest="rrf_k",
                   help="RRF constant for hybrid fusion (default: 60)")
    p.add_argument("--rerank", action="store_true",
                   help="Rerank step_02 output with Qwen3-Reranker-8B")
    p.add_argument("--rerank-pool", type=int, default=None, dest="rerank_pool",
                   help=f"Candidate pool fed to reranker (default: {DEFAULT_RERANK_OVERSAMPLE}x top-k-2)")
    p.add_argument("--rerank-url", default=DEFAULT_RERANK_URL, dest="rerank_url",
                   help=f"Reranker server base URL (default: {DEFAULT_RERANK_URL})")
    p.add_argument("--ef-search-1", type=int, default=None, dest="ef_search_1",
                   help="HNSW ef_search for step 1 (default: = top-k-1). Must be >= top-k-1.")
    p.add_argument("--ef-search-2", type=int, default=None, dest="ef_search_2",
                   help="HNSW ef_search for step 2 (default: = effective step-2 LIMIT).")
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
    ef1 = args.ef_search_1 if args.ef_search_1 is not None else args.top_k_1
    ef2 = args.ef_search_2 if args.ef_search_2 is not None else args.top_k_2
    strategy_str = ",".join(strategies) if strategies else "all"
    print(f"{summary} | top_k_1: {args.top_k_1} | top_k_2: {args.top_k_2} | "
          f"ef_search_1: {ef1} | ef_search_2: {ef2} | strategy: {strategy_str}")

    client = EmbedClient(base_url=args.embed_url)
    hybrid_mode = "bm25_only" if args.bm25_only else ("hybrid" if args.hybrid else None)
    reranker = RerankClient(base_url=args.rerank_url) if args.rerank else None
    rerank_pool = (
        args.rerank_pool
        if args.rerank_pool is not None
        else DEFAULT_RERANK_OVERSAMPLE * args.top_k_2
    )
    run_id = str(uuid.uuid4())

    flags = {
        "top_k_1": args.top_k_1,
        "top_k_2": args.top_k_2,
        "ef_search_1": ef1,
        "ef_search_2": ef2,
        "strategy": strategies if strategies is not None else "all",
        "source_types": source_types if source_types is not None else "all",
        "skip_voyage_key": args.no_voyage_key,
        "hybrid": hybrid_mode,
        "rrf_k": args.rrf_k if hybrid_mode is not None else None,
        "reranker": reranker is not None,
        "rerank_pool": rerank_pool if reranker is not None else None,
    }

    results: dict[str, dict] = {}
    with connect() as conn:
        email_thread_map = load_email_thread_map(conn)
        attach_email_map = load_attachment_email_map(conn)
        for category, rows in sorted(rows_by_category.items()):
            results[category] = _run_for_category(
                conn, client, rows, run_id,
                args.top_k_1, args.top_k_2, category,
                source_types=source_types, strategies=strategies,
                flags=flags,
                skip_voyage_key=args.no_voyage_key,
                email_thread_map=email_thread_map,
                attach_email_map=attach_email_map,
                hybrid_mode=hybrid_mode,
                rrf_k=args.rrf_k,
                reranker=reranker,
                rerank_pool=rerank_pool,
                ef_search_1=args.ef_search_1,
                ef_search_2=args.ef_search_2,
            )

    with connect() as conn:
        for category, r in results.items():
            total = r["total"]
            key_recall = r["key_hits"] / total if total else 0.0
            thread_recall = r["thread_hits"] / total if total else 0.0
            email_recall = r["email_hits"] / total if total else 0.0
            log_retrieval_run(
                conn,
                run_id=run_id,
                test_type="voyage_key_retrieval_e2e",
                question_type=category,
                top_k=args.top_k_1,
                total=total,
                thread_hits=r["key_hits"],
                thread_recall=key_recall,
                strategy=strategy_str,
                bm25=hybrid_mode is not None,
                reranker=reranker is not None,
                reformulator=False,
                ef=ef1,
            )
            log_retrieval_run(
                conn,
                run_id=run_id,
                test_type="chunk_retrieval_e2e",
                question_type=category,
                top_k=args.top_k_2,
                total=total,
                thread_hits=r["thread_hits"],
                thread_recall=thread_recall,
                email_hits=r["email_hits"],
                email_recall=email_recall,
                strategy=strategy_str,
                bm25=hybrid_mode is not None,
                reranker=reranker is not None,
                reformulator=False,
                ef=ef2,
            )

    print(f"\nDone. run_id={run_id} | strategy: {strategy_str}")
    for category, r in sorted(results.items()):
        total = r["total"]
        key_recall = r["key_hits"] / total if total else 0.0
        thread_recall = r["thread_hits"] / total if total else 0.0
        email_recall = r["email_hits"] / total if total else 0.0
        print(
            f"{category} ({total}): "
            f"key recall: {key_recall:.1%} || "
            f"thread recall: {thread_recall:.1%} MRR {r['thread_mrr']:.4f} | "
            f"email recall: {email_recall:.1%} MRR {r['email_mrr']:.4f}"
        )


if __name__ == "__main__":
    main()
