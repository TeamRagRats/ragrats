"""
Isolated chunk retrieval test — step 2 only.

Feeds the correct voyage_key from ground_truth_v2 directly to retrieve_chunks,
bypassing step 1 entirely. This measures how well step 2 performs given a
perfect voyage key, making it independent of step 1 errors.

Runs against ground_truth_v2 where every row has a NOT NULL source_chunk_id,
so all categories (logistics_cargo / commercial_terms / incident_decision)
are evaluated. Results are logged separately per category.

Run on SPARK where both postgres and the embed server are reachable:
    python run_test.py
    python run_test.py --top-k 20 --expand-window 2
    python run_test.py --num-queries 3          # enable multi-query
    python run_test.py --num-queries 1          # baseline (no expansion)
    python run_test.py --no-instruction         # disable instruction prefix
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
from step_00_query_expansion import expand_query
from step_02_chunk_retrieval.retrieve_chunks import retrieve_chunks, RetrievedChunk
from step_02_chunk_retrieval.expand_chunks import expand_chunks
from log.log_chunk_retrieval_testing import log_chunk_retrieval_testing
from log.log_testing import log_retrieval_run

_QUERY_INSTRUCTION = "Represent this search query for retrieving relevant maritime project documents: "


def _dedup_chunks(all_chunks: list[list[RetrievedChunk]]) -> list[RetrievedChunk]:
    best: dict[str, RetrievedChunk] = {}
    for chunks in all_chunks:
        for chunk in chunks:
            if chunk.chunk_id not in best or chunk.similarity > best[chunk.chunk_id].similarity:
                best[chunk.chunk_id] = chunk
    return sorted(best.values(), key=lambda c: c.similarity, reverse=True)


def _compute_chunk_rank(expected_chunk_id: str, chunks: list) -> int | None:
    for i, chunk in enumerate(chunks, 1):
        if chunk.chunk_id == expected_chunk_id:
            return i
    return None


def _run_for_category(
    conn,
    client: EmbedClient,
    rows: list,
    run_id: str,
    top_k: int,
    expand_window: int,
    category: str,
    num_queries: int = 1,
    use_instruction: bool = True,
    llm: LLMClient | None = None,
) -> tuple[int, int, float]:
    hits = 0
    mrr_sum = 0.0
    total = len(rows)

    for i, (question_id, question, expected_key, expected_chunk_id) in enumerate(rows, 1):
        queries = expand_query(question, n=num_queries - 1, llm=llm) if num_queries > 1 else [question]

        if use_instruction:
            queries = [_QUERY_INSTRUCTION + q for q in queries]

        embeddings = client.embed(queries)

        all_retrieved = [
            retrieve_chunks(conn, emb, voyage_keys=[expected_key], top_k=top_k)
            for emb in embeddings
        ]
        anchor_chunks = _dedup_chunks(all_retrieved)[:top_k]

        expanded_chunks = expand_chunks(conn, anchor_chunks, window=expand_window)

        expanded_chunk_ids = [c.chunk_id for c in expanded_chunks]
        rank = _compute_chunk_rank(expected_chunk_id, anchor_chunks)
        hit = expected_chunk_id in expanded_chunk_ids

        if hit:
            hits += 1
        if rank is not None:
            mrr_sum += 1.0 / rank

        log_chunk_retrieval_testing(
            conn,
            run_id=run_id,
            question_id=question_id,
            top_k=top_k,
            expected_source_id=expected_chunk_id,
            returned_source_ids=expanded_chunk_ids,
            hit=hit,
            source_rank=rank,
        )

        if i % 50 == 0:
            print(f"  [{category}] {i}/{total} — chunk recall: {hits/i:.1%}")

    mrr = mrr_sum / total if total else 0.0
    return hits, total, mrr


def main() -> None:
    p = argparse.ArgumentParser(description="Isolated chunk retrieval test (step 2 only)")
    p.add_argument("--top-k", type=int, default=20, dest="top_k",
                   help="Chunks to retrieve per question (default: 20)")
    p.add_argument("--expand-window", type=int, default=2, dest="expand_window",
                   help="Neighbor chunks on each side of an anchor (default: 2)")
    p.add_argument("--embed-url", default=DEFAULT_BASE_URL,
                   help=f"Embed server base URL (default: {DEFAULT_BASE_URL})")
    p.add_argument("--num-queries", type=int, default=1, dest="num_queries",
                   help="Query variants to generate per question (1 = baseline, default: 1)")
    p.add_argument("--no-instruction", action="store_true", dest="no_instruction",
                   help="Disable instruction prefix on embeddings")
    args = p.parse_args()

    with connect() as conn:
        all_rows = conn.execute("""
            SELECT question_id, question, voyage_key, source_chunk_id::text, category
            FROM ground_truth_v2
            ORDER BY category, question_id
        """).fetchall()

    rows_by_category: dict[str, list] = {}
    for question_id, question, voyage_key, source_chunk_id, category in all_rows:
        rows_by_category.setdefault(category, []).append(
            (question_id, question, voyage_key, source_chunk_id)
        )

    use_instruction = not args.no_instruction
    llm = LLMClient() if args.num_queries > 1 else None
    test_type = "chunk_retrieval_isolated_v2" + ("_mq" if args.num_queries > 1 else "")

    summary = " | ".join(f"{cat}: {len(rows)}" for cat, rows in sorted(rows_by_category.items()))
    print(f"{summary} | top_k: {args.top_k} | expand: ±{args.expand_window} | queries: {args.num_queries} | instruction: {use_instruction}")

    client = EmbedClient(base_url=args.embed_url)
    run_id = str(uuid.uuid4())

    results: dict[str, tuple[int, int, float]] = {}
    with connect() as conn:
        for category, rows in sorted(rows_by_category.items()):
            hits, total, mrr = _run_for_category(
                conn, client, rows, run_id, args.top_k, args.expand_window, category,
                num_queries=args.num_queries,
                use_instruction=use_instruction,
                llm=llm,
            )
            results[category] = (hits, total, mrr)

    with connect() as conn:
        for category, (hits, total, _) in results.items():
            recall = hits / total if total else 0.0
            log_retrieval_run(
                conn,
                run_id=run_id,
                test_type=test_type,
                question_type=category,
                top_k=args.top_k,
                total=total,
                hits=hits,
                recall=recall,
            )

    print(f"\nDone. run_id={run_id}")
    for category, (hits, total, mrr) in sorted(results.items()):
        recall = hits / total if total else 0.0
        print(f"{category} ({total}): chunk recall: {hits}/{total} ({recall:.1%}) | MRR: {mrr:.4f}")


if __name__ == "__main__":
    main()
