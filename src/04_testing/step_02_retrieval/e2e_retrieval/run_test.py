"""
End-to-end retrieval recall test — full pipeline (step 1 → step 2).

For every ground_truth_v3 row, embeds the question, runs the production
pipeline (find_winning_voyage_keys → retrieve_chunks) and checks:
  - voyage key recall:  expected_key in winning_keys (vote winners)
  - chunk recall:       expected (source_type, source_id, chunk_index)
                        matched by an anchor (chunk_index ignored when NULL)

Categories: fact_single / summary / reasoning / unanswerable. Voyage key and
chunk results are logged separately to test_retrieval_run_logging under the
same run_id; per-question chunk results to test_chunk_retrieval_logging.

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
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_retrieval))
    __package__ = "src.testing.retrieval.e2e"

import argparse
import uuid

from core.db import connect
from clients.embed_client import EmbedClient, DEFAULT_BASE_URL
from step_01_voyage_key import find_winning_voyage_keys
from step_02_chunk_retrieval.retrieve_chunks import retrieve_chunks
from filter_args import resolve_source_types, resolve_strategies
from log.log_chunk_retrieval_testing import log_chunk_retrieval_testing
from log.log_testing import log_retrieval_run


def _coord_str(source_type: str, source_id: str, chunk_index: int | None) -> str:
    return f"{source_type}:{source_id}" if chunk_index is None else f"{source_type}:{source_id}:{chunk_index}"


def _matches(chunk, expected_source_type: str, expected_source_id: str, expected_chunk_index: int | None) -> bool:
    if chunk.source_type != expected_source_type or chunk.source_id != expected_source_id:
        return False
    if expected_chunk_index is None:
        return True
    return chunk.chunk_index == expected_chunk_index


def _compute_rank(chunks: list, expected_source_type: str, expected_source_id: str, expected_chunk_index: int | None) -> int | None:
    for i, chunk in enumerate(chunks, 1):
        if _matches(chunk, expected_source_type, expected_source_id, expected_chunk_index):
            return i
    return None


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
    skip_voyage_key: bool,
) -> tuple[int, int, int, float]:
    key_hits = 0
    chunk_hits = 0
    mrr_sum = 0.0
    total = len(rows)

    for i, (question_id, question, expected_key, expected_source_type,
            expected_source_id, expected_chunk_index) in enumerate(rows, 1):
        embedding = client.embed([question])[0]

        if skip_voyage_key:
            winning_keys, vote_counts = [], {}
        else:
            winning_keys, vote_counts = find_winning_voyage_keys(
                conn, embedding, top_k=top_k_1,
                source_types=source_types, strategies=strategies,
            )
            if expected_key in vote_counts:
                key_hits += 1

        anchor_chunks = retrieve_chunks(
            conn, embedding,
            voyage_keys=winning_keys if winning_keys else None,
            top_k=top_k_2,
            source_types=source_types, strategies=strategies,
        )

        rank = _compute_rank(anchor_chunks, expected_source_type, expected_source_id, expected_chunk_index)
        hit = rank is not None

        if hit:
            chunk_hits += 1
            mrr_sum += 1.0 / rank

        log_chunk_retrieval_testing(
            conn,
            run_id=run_id,
            question_id=question_id,
            top_k=top_k_2,
            expected_source_id=_coord_str(expected_source_type, expected_source_id, expected_chunk_index),
            returned_source_ids=[c.chunk_id for c in anchor_chunks],
            hit=hit,
            source_rank=rank,
        )

        if i % 50 == 0:
            print(
                f"  [{category}] {i}/{total} — "
                f"key: {key_hits/i:.1%} | chunk: {chunk_hits/i:.1%}"
            )

    mrr = mrr_sum / total if total else 0.0
    return key_hits, chunk_hits, total, mrr


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
    args = p.parse_args()

    source_types = resolve_source_types(args.source_types)
    strategies = resolve_strategies(args.strategies)

    with connect() as conn:
        all_rows = conn.execute("""
            SELECT question_id, question, voyage_key, source_type, source_id, chunk_index, category
            FROM ground_truth_v3
            ORDER BY category, question_id
        """).fetchall()

    rows_by_category: dict[str, list] = {}
    for question_id, question, voyage_key, source_type, source_id, chunk_index, category in all_rows:
        rows_by_category.setdefault(category, []).append(
            (question_id, question, voyage_key, source_type, source_id, chunk_index)
        )

    summary = " | ".join(f"{cat}: {len(rows)}" for cat, rows in sorted(rows_by_category.items()))
    print(f"{summary} | top_k_1: {args.top_k_1} | top_k_2: {args.top_k_2}")

    client = EmbedClient(base_url=args.embed_url)
    run_id = str(uuid.uuid4())

    results: dict[str, tuple[int, int, int, float]] = {}
    with connect() as conn:
        for category, rows in sorted(rows_by_category.items()):
            key_hits, chunk_hits, total, mrr = _run_for_category(
                conn, client, rows, run_id,
                args.top_k_1, args.top_k_2, category,
                source_types=source_types, strategies=strategies,
                skip_voyage_key=args.no_voyage_key,
            )
            results[category] = (key_hits, chunk_hits, total, mrr)

    with connect() as conn:
        for category, (key_hits, chunk_hits, total, _) in results.items():
            key_recall = key_hits / total if total else 0.0
            chunk_recall = chunk_hits / total if total else 0.0
            log_retrieval_run(
                conn,
                run_id=run_id,
                test_type="voyage_key_retrieval_e2e_v3",
                question_type=category,
                top_k=args.top_k_1,
                total=total,
                hits=key_hits,
                recall=key_recall,
            )
            log_retrieval_run(
                conn,
                run_id=run_id,
                test_type="chunk_retrieval_e2e_v3",
                question_type=category,
                top_k=args.top_k_2,
                total=total,
                hits=chunk_hits,
                recall=chunk_recall,
            )

    print(f"\nDone. run_id={run_id}")
    for category, (key_hits, chunk_hits, total, mrr) in sorted(results.items()):
        key_recall = key_hits / total if total else 0.0
        chunk_recall = chunk_hits / total if total else 0.0
        print(
            f"{category} ({total}): "
            f"key recall: {key_recall:.1%} | chunk recall: {chunk_recall:.1%} | MRR: {mrr:.4f}"
        )


if __name__ == "__main__":
    main()
