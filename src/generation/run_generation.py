from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent          # src/generation/
    _repo_root = _here.parents[1]                     # repo root
    _retrieval = _repo_root / "src" / "retrieval"
    _preprocessing = _repo_root / "src" / "preprocessing"
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_here))                    # step_01_*, step_02_* (generation's own)
    sys.path.insert(0, str(_retrieval))              # step_01_voyage_key_precision, step_02_chunk_retrieval
    sys.path.insert(0, str(_preprocessing))           # shared.db, step_09_summaries, step_11_embedding
    __package__ = "src.generation"

import argparse
import json
import logging
import time
from pathlib import Path

from shared.db import connect
from step_11_embedding.embed_client import EmbedClient, DEFAULT_BASE_URL as DEFAULT_EMBED_URL
from step_09_summaries.llm_client import LLMClient, DEFAULT_BASE_URL as DEFAULT_LLM_URL

from step_01_voyage_key_precision import find_winning_voyage_keys
from step_02_chunk_retrieval import retrieve_chunks
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


def _log_retrieval_to_db(
    conn,
    *,
    query: str,
    source_types: list[str] | None,
    top_k_1: int,
    top_k_2: int,
    winning_keys: list[str],
    key_vote_counts: dict[str, int],
    step1_ms: int,
    step2_ms: int,
    total_ms: int,
    chunks_returned: int,
    chunks: list,
) -> str:
    chunks_json = json.dumps([
        {
            "chunk_id": c.chunk_id,
            "voyage_key": c.voyage_key,
            "source_type": c.source_type,
            "source_id": c.source_id,
            "chunk_index": c.chunk_index,
            "similarity": round(c.similarity, 4),
            "text": c.text,
        }
        for c in chunks
    ])
    row = conn.execute(
        """
        INSERT INTO retrieval_logging
            (query, source_types, top_k_1, top_k_2, winning_keys, key_vote_counts,
             step1_ms, step2_ms, total_ms, chunks_returned, chunks)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb)
        RETURNING run_id
        """,
        (
            query,
            source_types,
            top_k_1,
            top_k_2,
            winning_keys,
            json.dumps(key_vote_counts),
            step1_ms,
            step2_ms,
            total_ms,
            chunks_returned,
            chunks_json,
        ),
    ).fetchone()
    conn.commit()
    return str(row[0])


def _log_generation_to_db(
    conn,
    *,
    retrieval_run_id: str,
    query: str,
    answer: str,
    system_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    prompt_tokens: int,
    completion_tokens: int,
    generation_ms: int,
    total_ms: int,
) -> None:
    conn.execute(
        """
        INSERT INTO generation_logging
            (retrieval_run_id, query, answer, system_prompt, model, temperature,
             max_tokens, prompt_tokens, completion_tokens, generation_ms, total_ms)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            retrieval_run_id, query, answer, system_prompt, model, temperature,
            max_tokens, prompt_tokens, completion_tokens, generation_ms, total_ms,
        ),
    )
    conn.commit()


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
    args = p.parse_args()

    source_types = _resolve_source_types(args.source_types)

    logger.info(f"Embedding query: {args.query!r}")
    client = EmbedClient(base_url=args.embed_url)
    embedding = client.embed([args.query])[0]

    t_total = time.monotonic()

    with connect() as conn:
        t1 = time.monotonic()
        winning_keys, vote_counts = find_winning_voyage_keys(
            conn, embedding, top_k=args.top_k_1, source_types=source_types
        )
        step1_ms = int((time.monotonic() - t1) * 1000)

        if not winning_keys:
            logger.error("No chunks found — is temporary_chunks populated?")
            return

        top_vote = vote_counts[winning_keys[0]]
        logger.info(
            f"[step1] Winner(s): {winning_keys} — {top_vote}/{args.top_k_1} votes — {step1_ms}ms"
        )

        t2 = time.monotonic()
        chunks = retrieve_chunks(
            conn, embedding, voyage_keys=winning_keys, top_k=args.top_k_2, source_types=source_types
        )
        step2_ms = int((time.monotonic() - t2) * 1000)

        logger.info(f"[step2] Retrieved {len(chunks)} chunks — {step2_ms}ms")

        retrieval_run_id = _log_retrieval_to_db(
            conn,
            query=args.query,
            source_types=source_types if source_types is not None else ["all"],
            top_k_1=args.top_k_1,
            top_k_2=args.top_k_2,
            winning_keys=winning_keys,
            key_vote_counts=vote_counts,
            step1_ms=step1_ms,
            step2_ms=step2_ms,
            total_ms=int((time.monotonic() - t_total) * 1000),
            chunks_returned=len(chunks),
            chunks=chunks,
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

        llm = LLMClient(base_url=args.llm_url)
        t_gen = time.monotonic()
        answer, usage = generate_answer(
            llm, args.query, context, _DEFAULT_SYSTEM_PROMPT, args.temperature, args.max_tokens
        )
        generation_ms = int((time.monotonic() - t_gen) * 1000)

        total_ms = int((time.monotonic() - t_total) * 1000)

        _log_generation_to_db(
            conn,
            retrieval_run_id=retrieval_run_id,
            query=args.query,
            answer=answer,
            system_prompt=_DEFAULT_SYSTEM_PROMPT,
            model=llm.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            generation_ms=generation_ms,
            total_ms=total_ms,
        )

    print(answer)

    logger.info(f"[generation] {generation_ms}ms")
    logger.info(f"[total] {total_ms}ms")


if __name__ == "__main__":
    main()
