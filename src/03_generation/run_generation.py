from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent          # src/03_generation/
    _repo_root = _here.parents[1]                     # repo root
    _retrieval = _repo_root / "src" / "02_retrieval"
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_here))                    # step_01_*, step_02_* (generation's own)
    sys.path.insert(0, str(_retrieval))              # step_01_voyage_key, step_02_chunk_retrieval
    __package__ = "src.generation"

import argparse
import logging
import time
from pathlib import Path

from core.db import connect
from log.log_retrieval import log_retrieval
from log.log_generation import log_generation
from log.log_query import log_query
from clients.embed_client import EmbedClient, DEFAULT_BASE_URL as DEFAULT_EMBED_URL
from clients.llm_client import LLMClient, DEFAULT_BASE_URL as DEFAULT_LLM_URL
from clients.rerank_client import RerankClient, DEFAULT_BASE_URL as DEFAULT_RERANK_URL

from step_00_query_reformulation import reformulate_query
from step_01_voyage_key import find_winning_voyage_keys
from step_02_chunk_retrieval import retrieve_chunks, hybrid_retrieve_chunks
from step_03_rerank import rerank_chunks, DEFAULT_RERANK_OVERSAMPLE
from step_01_build_context import build_context
from step_02_llm_generation import generate_answer
from filter_args import (
    resolve_source_types, resolve_strategies, resolve_chunkers,
    DEFAULT_STRATEGIES, DEFAULT_CHUNKERS,
)

_REPO_ROOT = Path(__file__).parents[2]
_DEFAULT_SYSTEM_PROMPT = (
    _REPO_ROOT / "system_prompts" / "generation" / "generation.md"
).read_text(encoding="utf-8").strip()


def run_query(
    query: str,
    username: str,
    source: str = "terminal",
    session_id: str | None = None,
    top_k_1: int = 500,
    top_k_2: int = 20,
    temperature: float = 0.3,
    max_tokens: int = 2500,
    source_types: list[str] | None = None,
    strategies: list[str] | None = None,
    chunkers: list[str] | None = None,
    hybrid: bool = False,
    skip_voyage_key: bool = False,
    system_prompt: str | None = None,
    rerank: bool = False,
    rerank_pool: int | None = None,
    rerank_url: str | None = None,
    ef_search_1: int | None = None,
    ef_search_2: int | None = None,
) -> tuple[str, str]:
    """Run the full RAG pipeline and return the answer. Logs query, retrieval, and generation."""
    if system_prompt is None:
        system_prompt = _DEFAULT_SYSTEM_PROMPT

    llm = LLMClient()
    retrieval_query = reformulate_query(llm, query)

    embed_client = EmbedClient()
    embedding = embed_client.embed([retrieval_query])[0]

    t_total = time.monotonic()

    with connect() as conn:
        if skip_voyage_key:
            winning_keys: list[str] = []
            vote_counts: dict[str, int] = {}
            step1_ms = 0
        else:
            t1 = time.monotonic()
            winning_keys, vote_counts = find_winning_voyage_keys(
                conn, embedding, top_k=top_k_1,
                source_types=source_types, strategies=strategies, chunkers=chunkers,
                ef_search=ef_search_1,
            )
            step1_ms = int((time.monotonic() - t1) * 1000)

            if not winning_keys:
                return "", ""

        effective_rerank_pool = (
            rerank_pool if rerank_pool is not None else DEFAULT_RERANK_OVERSAMPLE * top_k_2
        )
        step2_top_k = effective_rerank_pool if rerank else top_k_2

        t2 = time.monotonic()
        if hybrid:
            chunks = hybrid_retrieve_chunks(
                conn,
                query_text=query,
                query_embedding=embedding,
                voyage_keys=winning_keys if winning_keys else None,
                top_k=step2_top_k,
                source_types=source_types,
                strategies=strategies,
                chunkers=chunkers,
                ef_search=ef_search_2,
            )
        else:
            chunks = retrieve_chunks(
                conn, embedding,
                voyage_keys=winning_keys if winning_keys else None,
                top_k=step2_top_k,
                source_types=source_types,
                strategies=strategies,
                chunkers=chunkers,
                ef_search=ef_search_2,
            )
        step2_ms = int((time.monotonic() - t2) * 1000)

        rerank_ms: int | None = None
        rerank_model: str | None = None
        if rerank and chunks:
            rerank_client = RerankClient(
                base_url=rerank_url if rerank_url is not None else DEFAULT_RERANK_URL,
            )
            rerank_model = rerank_client.model
            t_r = time.monotonic()
            chunks = rerank_chunks(rerank_client, query, chunks, top_k=top_k_2)
            rerank_ms = int((time.monotonic() - t_r) * 1000)

        if not chunks:
            return "", ""

        query_id = log_query(conn, query, source=source, username=username, session_id=session_id)

        log_retrieval(
            conn,
            query_id=query_id,
            query_text=query,
            source_types=source_types if source_types is not None else ["all"],
            strategy=strategies if strategies is not None else DEFAULT_STRATEGIES,
            chunker=chunkers if chunkers is not None else DEFAULT_CHUNKERS,
            top_k_1=top_k_1,
            top_k_2=top_k_2,
            winning_keys=winning_keys,
            key_vote_counts=vote_counts,
            step1_ms=step1_ms,
            step2_ms=step2_ms,
            total_ms=int((time.monotonic() - t_total) * 1000),
            chunks_returned=len(chunks),
            chunks=chunks,
            chunks_expanded_returned=0,
            chunks_expanded=None,
            reranked=rerank,
            rerank_model=rerank_model,
            rerank_pool=effective_rerank_pool if rerank else None,
            rerank_ms=rerank_ms,
            ef_search_1=(
                None if skip_voyage_key
                else (ef_search_1 if ef_search_1 is not None else top_k_1)
            ),
            ef_search_2=(ef_search_2 if ef_search_2 is not None else step2_top_k),
            embed_input=retrieval_query,
        )

        context = build_context(conn, chunks, winning_keys)

        t_gen = time.monotonic()
        answer, usage, llm_input = generate_answer(
            llm, query, context, system_prompt, temperature, max_tokens
        )
        generation_ms = int((time.monotonic() - t_gen) * 1000)
        total_ms = int((time.monotonic() - t_total) * 1000)

        log_generation(
            conn,
            query_id=query_id,
            query_text=query,
            answer=answer,
            system_prompt=system_prompt,
            model=llm.model,
            temperature=temperature,
            max_tokens=max_tokens,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            generation_ms=generation_ms,
            total_ms=total_ms,
            llm_input=llm_input,
        )

    return answer, query_id


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("generation")

    p = argparse.ArgumentParser(description="Retrieval + LLM generation pipeline")
    p.add_argument("--query", required=True, help="Natural language query")
    p.add_argument("--top-k-1", type=int, default=500, dest="top_k_1",
                   help="Candidates for voyage_key selection (default: 500)")
    p.add_argument("--top-k-2", type=int, default=20, dest="top_k_2",
                   help="Final chunk count (default: 20)")
    p.add_argument("--source-type", action="append", dest="source_types", metavar="TYPE",
                   help="Filter by source type: email, attachment, all (repeatable; default: email + attachment)")
    p.add_argument("--strategy", action="append", dest="strategies", metavar="STRATEGY",
                   help="Filter by embedding strategy: plain, late, context, summary, all (repeatable; default: plain)")
    p.add_argument("--chunker", action="append", dest="chunkers", metavar="CHUNKER",
                   help="Filter by chunk collection label: e.g. 1500, 1000, naive, all "
                        "(repeatable; default: 1500). 'all' blends every size.")
    p.add_argument("--no-voyage-key", action="store_true", dest="no_voyage_key",
                   help="Skip step 1 (voyage_key voting); retrieve chunks across the whole index")
    p.add_argument("--embed-url", default=DEFAULT_EMBED_URL,
                   help=f"Embed server base URL (default: {DEFAULT_EMBED_URL})")
    p.add_argument("--llm-url", default=DEFAULT_LLM_URL,
                   help=f"LLM server base URL (default: {DEFAULT_LLM_URL})")
    p.add_argument("--temperature", type=float, default=0.3,
                   help="LLM sampling temperature (default: 0.3)")
    p.add_argument("--max-tokens", type=int, default=2500, dest="max_tokens",
                   help="LLM max output tokens (default: 2500)")
    p.add_argument("--rerank", action="store_true",
                   help="Rerank retrieved chunks with Qwen3-Reranker-8B before generation")
    p.add_argument("--rerank-pool", type=int, default=None, dest="rerank_pool",
                   help=f"Candidate pool fed to reranker (default: {DEFAULT_RERANK_OVERSAMPLE}x top-k-2)")
    p.add_argument("--rerank-url", default=DEFAULT_RERANK_URL, dest="rerank_url",
                   help=f"Reranker server base URL (default: {DEFAULT_RERANK_URL})")
    p.add_argument("--ef-search-1", type=int, default=None, dest="ef_search_1",
                   help="HNSW ef_search for step 1 (default: = top-k-1). Must be >= top-k-1.")
    p.add_argument("--ef-search-2", type=int, default=None, dest="ef_search_2",
                   help="HNSW ef_search for step 2 (default: = effective step-2 LIMIT). "
                        "Must be >= that LIMIT.")
    args = p.parse_args()

    source_types = resolve_source_types(args.source_types)
    strategies = resolve_strategies(args.strategies)
    chunkers = resolve_chunkers(args.chunkers)

    logger.info(f"Running query: {args.query!r}")

    answer, _query_id = run_query(
        query=args.query,
        username="developer",
        source="terminal",
        top_k_1=args.top_k_1,
        top_k_2=args.top_k_2,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        source_types=source_types,
        strategies=strategies,
        chunkers=chunkers,
        skip_voyage_key=args.no_voyage_key,
        rerank=args.rerank,
        rerank_pool=args.rerank_pool,
        rerank_url=args.rerank_url,
        ef_search_1=args.ef_search_1,
        ef_search_2=args.ef_search_2,
    )

    if not answer:
        logger.error("No chunks found — is the chunks table populated?")
        return

    print(answer)
    logger.info("Done")


if __name__ == "__main__":
    main()
