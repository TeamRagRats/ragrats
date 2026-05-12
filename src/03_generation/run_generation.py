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

from step_01_voyage_key import find_winning_voyage_keys
from step_02_chunk_retrieval import retrieve_chunks
from step_01_context_builder import build_context
from step_02_llm_generation import generate_answer
from filter_args import resolve_source_types, resolve_strategies, DEFAULT_STRATEGIES

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
    skip_voyage_key: bool = False,
    system_prompt: str | None = None,
) -> tuple[str, str]:
    """Run the full RAG pipeline and return the answer. Logs query, retrieval, and generation."""
    if system_prompt is None:
        system_prompt = _DEFAULT_SYSTEM_PROMPT

    embed_client = EmbedClient()
    embedding = embed_client.embed([query])[0]

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
                source_types=source_types, strategies=strategies,
            )
            step1_ms = int((time.monotonic() - t1) * 1000)

            if not winning_keys:
                return "", ""

        t2 = time.monotonic()
        chunks = retrieve_chunks(
            conn, embedding,
            voyage_keys=winning_keys if winning_keys else None,
            top_k=top_k_2,
            source_types=source_types,
            strategies=strategies,
        )
        step2_ms = int((time.monotonic() - t2) * 1000)

        if not chunks:
            return "", ""

        query_id = log_query(conn, query, source=source, username=username, session_id=session_id)

        log_retrieval(
            conn,
            query_id=query_id,
            query_text=query,
            source_types=source_types if source_types is not None else ["all"],
            strategy=strategies if strategies is not None else DEFAULT_STRATEGIES,
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
        )

        context = build_context([
            {
                "chunk_id": c.chunk_id,
                "voyage_key": c.voyage_key,
                "source_type": c.source_type,
                "source_id": c.source_id,
                "chunk_index": c.chunk_index,
                "similarity": c.similarity,
                "text": c.text,
            }
            for c in chunks
        ])

        llm = LLMClient()
        t_gen = time.monotonic()
        answer, usage = generate_answer(
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
                   help="Filter by embedding strategy: plain, late, context, summary, all (repeatable; default: late)")
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
    args = p.parse_args()

    source_types = resolve_source_types(args.source_types)
    strategies = resolve_strategies(args.strategies)

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
        skip_voyage_key=args.no_voyage_key,
    )

    if not answer:
        logger.error("No chunks found — is the chunks table populated?")
        return

    print(answer)
    logger.info("Done")


if __name__ == "__main__":
    main()
