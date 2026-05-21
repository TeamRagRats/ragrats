"""
Isolated chunk retrieval test — step 2 only.

Feeds the correct voyage_key from ground_truth directly to retrieve_chunks,
bypassing step 1 entirely. This measures how well step 2 performs given a
perfect voyage key, making it independent of step 1 errors.

Reports two recall levels per question:
  - thread recall : any retrieved chunk lands in the same email thread as the
                    ground-truth email (loose; the previous "source recall")
  - email  recall : the retrieved chunk's parent email == ground-truth source_id
                    (strict; email_hit always implies thread_hit)

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
    _step02_testing = _here.parent
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_retrieval))
    sys.path.insert(0, str(_step02_testing))
    sys.path.insert(0, str(_here))
    __package__ = "src.testing.retrieval.chunk"

import uuid

from core.db import connect
from clients.embed_client import EmbedClient
from clients.llm_client import LLMClient
from clients.rerank_client import RerankClient
from log.log_chunk_retrieval_testing import log_chunk_retrieval_testing
from log.log_testing import log_retrieval_run

from source_match import (
    canonical_email,
    canonical_thread,
    compute_email_rank,
    compute_thread_rank,
    load_attachment_email_map,
    load_email_thread_map,
    serialize_chunks,
)
from cli import parse_args, resolve_config
from data import load_ground_truth
from pipeline import retrieve_for_question


def _run_for_category(
    conn,
    *,
    client: EmbedClient,
    llm: LLMClient | None,
    reranker: RerankClient | None,
    rows: list,
    run_id: str,
    category: str,
    top_k: int,
    rerank_pool: int,
    hybrid_mode: str | None,
    rrf_k: int,
    source_types: list[str] | None,
    strategies: list[str] | None,
    ef_search: int | None,
    flags: dict,
    email_thread_map: dict[str, str],
    attach_email_map: dict[str, str],
) -> dict:
    thread_hits = 0
    thread_mrr_sum = 0.0
    email_hits = 0
    email_mrr_sum = 0.0
    total = len(rows)

    for i, (question_id, question, expected_key, expected_source_type,
            expected_source_id, expected_strategy) in enumerate(rows, 1):
        chunks = retrieve_for_question(
            conn,
            client=client, llm=llm, reranker=reranker,
            question=question, expected_key=expected_key,
            top_k=top_k, rerank_pool=rerank_pool,
            hybrid_mode=hybrid_mode, rrf_k=rrf_k,
            source_types=source_types, strategies=strategies,
            ef_search=ef_search,
        )

        expected_email_id = expected_source_id if expected_source_type == "email" else None
        expected_thread_id = (
            email_thread_map.get(expected_source_id) if expected_source_type == "email" else None
        )
        expected_canonical = canonical_thread(
            expected_source_type, expected_source_id, expected_strategy,
            email_thread_map, attach_email_map,
        )

        thread_rank = compute_thread_rank(
            chunks, expected_canonical, email_thread_map, attach_email_map,
        )
        email_rank = compute_email_rank(chunks, expected_email_id, attach_email_map)
        thread_hit = thread_rank is not None
        email_hit = email_rank is not None
        if thread_hit:
            thread_hits += 1
            thread_mrr_sum += 1.0 / thread_rank
        if email_hit:
            email_hits += 1
            email_mrr_sum += 1.0 / email_rank

        returned_email_ids = [
            canonical_email(c.source_type, c.source_id, c.strategy, attach_email_map)
            for c in chunks
        ]
        returned_thread_ids = [
            canonical_thread(
                c.source_type, c.source_id, c.strategy,
                email_thread_map, attach_email_map,
            )
            for c in chunks
        ]
        log_chunk_retrieval_testing(
            conn,
            run_id=run_id,
            question_id=question_id,
            category=category,
            question=question,
            expected_email=expected_email_id,
            expected_thread=expected_thread_id,
            returned_email_ids=returned_email_ids,
            returned_thread_ids=returned_thread_ids,
            thread_hit=thread_hit,
            thread_rank=thread_rank,
            email_hit=email_hit,
            email_rank=email_rank,
            chunks=serialize_chunks(chunks),
            flags=flags,
        )

        if i % 50 == 0:
            print(
                f"  [{category}] {i}/{total} — "
                f"thread: {thread_hits/i:.1%} | email: {email_hits/i:.1%}"
            )

    thread_mrr = thread_mrr_sum / total if total else 0.0
    email_mrr = email_mrr_sum / total if total else 0.0
    return {
        "total": total,
        "thread_hits": thread_hits,
        "thread_mrr": thread_mrr,
        "email_hits": email_hits,
        "email_mrr": email_mrr,
    }


def main() -> None:
    args = parse_args()
    config = resolve_config(args)

    with connect() as conn:
        rows_by_category = load_ground_truth(conn, args.voyage)

    summary = " | ".join(f"{cat}: {len(rows)}" for cat, rows in sorted(rows_by_category.items()))
    print(f"{summary} | top_k: {args.top_k} | ef_search: {config['ef']} "
          f"| strategy: {config['strategy_str']}")

    client = EmbedClient(base_url=args.embed_url)
    llm = LLMClient() if args.reformulate else None
    reranker = RerankClient(base_url=args.rerank_url) if args.rerank else None
    run_id = str(uuid.uuid4())

    results: dict[str, dict] = {}
    with connect() as conn:
        email_thread_map = load_email_thread_map(conn)
        attach_email_map = load_attachment_email_map(conn)
        for category, rows in sorted(rows_by_category.items()):
            results[category] = _run_for_category(
                conn,
                client=client, llm=llm, reranker=reranker,
                rows=rows, run_id=run_id, category=category,
                top_k=args.top_k, rerank_pool=config["rerank_pool"],
                hybrid_mode=config["hybrid_mode"], rrf_k=args.rrf_k,
                source_types=config["source_types"], strategies=config["strategies"],
                ef_search=args.ef_search,
                flags=config["flags"],
                email_thread_map=email_thread_map,
                attach_email_map=attach_email_map,
            )

    with connect() as conn:
        for category, r in results.items():
            total = r["total"]
            thread_recall = r["thread_hits"] / total if total else 0.0
            email_recall = r["email_hits"] / total if total else 0.0
            log_retrieval_run(
                conn,
                run_id=run_id,
                test_type="chunk_retrieval",
                question_type=category,
                top_k=args.top_k,
                total=total,
                thread_hits=r["thread_hits"],
                thread_recall=thread_recall,
                email_hits=r["email_hits"],
                email_recall=email_recall,
                strategy=config["strategy_str"],
                bm25=config["hybrid_mode"] is not None,
                reranker=reranker is not None,
                reformulator=llm is not None,
                ef=config["ef"],
            )

    print(f"\nDone. run_id={run_id} | strategy: {config['strategy_str']}")
    for category, r in sorted(results.items()):
        total = r["total"]
        thread_recall = r["thread_hits"] / total if total else 0.0
        email_recall = r["email_hits"] / total if total else 0.0
        print(
            f"{category} ({total}): "
            f"thread recall: {r['thread_hits']}/{total} ({thread_recall:.1%}) MRR {r['thread_mrr']:.4f} | "
            f"email recall: {r['email_hits']}/{total} ({email_recall:.1%}) MRR {r['email_mrr']:.4f}"
        )


if __name__ == "__main__":
    main()
