from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent          # src/02_retrieval/
    _repo_root = _here.parents[1]                     # repo root
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_here))                    # step_01_*, step_02_*
    __package__ = "src.retrieval"

import argparse
import json
import logging
import time

from core.db import connect
from log.log_retrieval import log_retrieval
from log.log_query import log_query
from clients.embed_client import EmbedClient, DEFAULT_BASE_URL
from clients.llm_client import LLMClient

from step_00_query_expansion import expand_query
from step_01_voyage_key import find_winning_voyage_keys
from step_02_chunk_retrieval import retrieve_chunks, RetrievedChunk, expand_chunks

_SOURCE_TYPE_MAP = {
    "thread": "thread",
    "threads": "thread",
    "email-attach": "email_attach",
    "email_attach": "email_attach",
    "fixture": "fixture",
    "phase": "phase",
}

_QUERY_INSTRUCTION = "Represent this search query for retrieving relevant maritime project documents: "


def _resolve_source_types(raw: list[str] | None) -> list[str] | None:
    if not raw or "all" in raw:
        return None
    resolved: list[str] = []
    for t in raw:
        mapped = _SOURCE_TYPE_MAP.get(t.lower())
        if mapped is None:
            raise ValueError(
                f"Unknown source-type: {t!r}. Valid: all, thread, email-attach, fixture, phase"
            )
        if mapped not in resolved:
            resolved.append(mapped)
    return resolved or None


def _merge_vote_counts(all_counts: list[dict[str, int]]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for counts in all_counts:
        for key, count in counts.items():
            merged[key] = merged.get(key, 0) + count
    return merged


def _dedup_chunks(all_chunks: list[list[RetrievedChunk]]) -> list[RetrievedChunk]:
    """Merge chunks from multiple queries, keeping highest similarity per chunk_id."""
    best: dict[str, RetrievedChunk] = {}
    for chunks in all_chunks:
        for chunk in chunks:
            if chunk.chunk_id not in best or chunk.similarity > best[chunk.chunk_id].similarity:
                best[chunk.chunk_id] = chunk
    return sorted(best.values(), key=lambda c: c.similarity, reverse=True)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("retrieve")

    p = argparse.ArgumentParser(description="Two-step retrieval from chunks")
    p.add_argument("--query", required=True, help="Natural language query")
    p.add_argument("--top-k-1", type=int, default=500, dest="top_k_1",
                   help="Candidates for voyage_key selection (default: 500)")
    p.add_argument("--top-k-2", type=int, default=20, dest="top_k_2",
                   help="Final chunk count (default: 20)")
    p.add_argument("--source-type", action="append", dest="source_types", metavar="TYPE",
                   help="Filter by source type: all, thread, email-attach, fixture, phase (repeatable)")
    p.add_argument("--embed-url", default=DEFAULT_BASE_URL,
                   help=f"Embed server base URL (default: {DEFAULT_BASE_URL})")
    p.add_argument("--expand-window", type=int, default=2, dest="expand_window",
                   help="Neighbor chunks to fetch on each side of an anchor (default: 2)")
    p.add_argument("--num-queries", type=int, default=3, dest="num_queries",
                   help="Number of query variants to generate (1 = disable multi-query, default: 3)")
    args = p.parse_args()

    source_types = _resolve_source_types(args.source_types)

    # --- Query expansion ---
    t_expand = time.monotonic()
    if args.num_queries > 1:
        llm = LLMClient()
        queries = expand_query(args.query, n=args.num_queries - 1, llm=llm)
        logger.info(f"[expand] {len(queries)} queries in {int((time.monotonic() - t_expand) * 1000)}ms: {queries}")
    else:
        queries = [args.query]

    # --- Embed all queries with instruction prefix ---
    embed_client = EmbedClient(base_url=args.embed_url)
    instructed = [_QUERY_INSTRUCTION + q for q in queries]
    embeddings = embed_client.embed(instructed)
    logger.info(f"[embed] {len(embeddings)} embeddings")

    t_total = time.monotonic()

    with connect() as conn:
        # Step 1: merge vote counts across all query embeddings
        t1 = time.monotonic()
        all_vote_counts: list[dict[str, int]] = []
        for emb in embeddings:
            _, counts = find_winning_voyage_keys(
                conn, emb, top_k=args.top_k_1, source_types=source_types
            )
            all_vote_counts.append(counts)

        merged_votes = _merge_vote_counts(all_vote_counts)
        step1_ms = int((time.monotonic() - t1) * 1000)

        if not merged_votes:
            logger.error("No chunks found — is the chunks table populated?")
            return

        max_votes = max(merged_votes.values())
        winning_keys = [k for k, v in merged_votes.items() if v == max_votes]
        logger.info(
            f"[step1] Winner(s): {winning_keys} — {max_votes} merged votes — {step1_ms}ms"
        )

        # Step 2: retrieve chunks for each embedding, then deduplicate
        t2 = time.monotonic()
        all_retrieved: list[list[RetrievedChunk]] = []
        for emb in embeddings:
            chunks = retrieve_chunks(
                conn, emb, voyage_keys=winning_keys, top_k=args.top_k_2, source_types=source_types
            )
            all_retrieved.append(chunks)

        chunks = _dedup_chunks(all_retrieved)[: args.top_k_2]
        step2_ms = int((time.monotonic() - t2) * 1000)

        logger.info(f"[step2] Retrieved {len(chunks)} unique chunks — {step2_ms}ms")

        expanded = expand_chunks(conn, chunks, window=args.expand_window)
        logger.info(f"[expand] {len(chunks)} chunks → {len(expanded)} after ±{args.expand_window} expansion")

        total_ms = int((time.monotonic() - t_total) * 1000)
        logger.info(f"[total] {total_ms}ms")

        query_id = log_query(conn, args.query, source="terminal", username="developer")

        log_retrieval(
            conn,
            query_id=query_id,
            query_text=args.query,
            source_types=source_types if source_types is not None else ["all"],
            top_k_1=args.top_k_1,
            top_k_2=args.top_k_2,
            winning_keys=winning_keys,
            key_vote_counts=merged_votes,
            step1_ms=step1_ms,
            step2_ms=step2_ms,
            total_ms=total_ms,
            chunks_returned=len(chunks),
            chunks=chunks,
            chunks_expanded_returned=len(expanded),
            chunks_expanded=expanded,
        )

    for chunk in expanded:
        print(json.dumps(
            {
                "chunk_id": chunk.chunk_id,
                "voyage_key": chunk.voyage_key,
                "source_type": chunk.source_type,
                "source_id": chunk.source_id,
                "chunk_index": chunk.chunk_index,
                "similarity": round(chunk.similarity, 4),
                "text": chunk.text,
            },
            ensure_ascii=False,
        ))


if __name__ == "__main__":
    main()
