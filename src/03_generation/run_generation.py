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
from step_02_chunk_retrieval import retrieve_chunks, expand_chunks
from step_01_context_builder import build_context
from step_02_llm_generation import generate_answer

_REPO_ROOT = Path(__file__).parents[2]
_DEFAULT_SYSTEM_PROMPT = (
    _REPO_ROOT / "system_prompts" / "generation" / "generation.md"
).read_text(encoding="utf-8").strip()

_SOURCE_TYPE_MAP = {
    "thread": "thread",
    "threads": "thread",
    "email-attach": "email_attach",
    "email_attach": "email_attach",
    "fixture": "fixture",
    "phase": "phase",
}


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


def run_query(
    query: str,
    username: str,
    source: str = "terminal",
    session_id: str | None = None,
    top_k_1: int = 500,
    top_k_2: int = 20,
    expand_window: int = 2,
    temperature: float = 0.3,
    max_tokens: int = 2500,
    source_types: list[str] | None = None,
    system_prompt: str | None = None,
) -> str:
    """Run the full RAG pipeline and return the answer. Logs query, retrieval, and generation."""
    if system_prompt is None:
        system_prompt = _DEFAULT_SYSTEM_PROMPT

    embed_client = EmbedClient()
    embedding = embed_client.embed([query])[0]

    t_total = time.monotonic()

    with connect() as conn:
        t1 = time.monotonic()
        winning_keys, vote_counts = find_winning_voyage_keys(
            conn, embedding, top_k=top_k_1, source_types=source_types
        )
        step1_ms = int((time.monotonic() - t1) * 1000)

        if not winning_keys:
            return ""

        t2 = time.monotonic()
        chunks = retrieve_chunks(
            conn, embedding, voyage_keys=winning_keys, top_k=top_k_2, source_types=source_types
        )
        step2_ms = int((time.monotonic() - t2) * 1000)

        expanded = expand_chunks(conn, chunks, window=expand_window)

        query_id = log_query(conn, query, source=source, username=username, session_id=session_id)

        log_retrieval(
            conn,
            query_id=query_id,
            query_text=query,
            source_types=source_types if source_types is not None else ["all"],
            top_k_1=top_k_1,
            top_k_2=top_k_2,
            winning_keys=winning_keys,
            key_vote_counts=vote_counts,
            step1_ms=step1_ms,
            step2_ms=step2_ms,
            total_ms=int((time.monotonic() - t_total) * 1000),
            chunks_returned=len(chunks),
            chunks=chunks,
            chunks_expanded_returned=len(expanded),
            chunks_expanded=expanded,
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
            for c in expanded
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

    return answer


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
                   help="Filter by source type: all, thread, email-attach, fixture, phase (repeatable)")
    p.add_argument("--embed-url", default=DEFAULT_EMBED_URL,
                   help=f"Embed server base URL (default: {DEFAULT_EMBED_URL})")
    p.add_argument("--llm-url", default=DEFAULT_LLM_URL,
                   help=f"LLM server base URL (default: {DEFAULT_LLM_URL})")
    p.add_argument("--temperature", type=float, default=0.3,
                   help="LLM sampling temperature (default: 0.3)")
    p.add_argument("--max-tokens", type=int, default=2500, dest="max_tokens",
                   help="LLM max output tokens (default: 2500)")
    p.add_argument("--expand-window", type=int, default=2, dest="expand_window",
                   help="Neighbor chunks to fetch on each side of an anchor (default: 2)")
    args = p.parse_args()

    source_types = _resolve_source_types(args.source_types)

    logger.info(f"Running query: {args.query!r}")

    answer = run_query(
        query=args.query,
        username="developer",
        source="terminal",
        top_k_1=args.top_k_1,
        top_k_2=args.top_k_2,
        expand_window=args.expand_window,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        source_types=source_types,
    )

    if not answer:
        logger.error("No chunks found — is the chunks table populated?")
        return

    print(answer)
    logger.info("Done")


if __name__ == "__main__":
    main()
