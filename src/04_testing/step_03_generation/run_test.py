"""
Generation accuracy test.

Joins ground_truth with test_retrieval_chunk_logging on question_id,
keeping only rows where hit=true (the correct source was retrieved).

Scores each generated answer against the ground_truth answer using:
  - cosine similarity between embeddings (objective baseline)
  - LLM-as-judge 1-5 score (qualitative signal, same-model bias acknowledged)

Results are broken down per category (fact_single, summary, reasoning, unanswerable).

Run on SPARK where postgres, the embed server, and the LLM are reachable:
    python run_test.py --retrieval-run-id <UUID>
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _repo_root = _here.parents[2]
    _generation = _repo_root / "src" / "03_generation"
    _retrieval = _repo_root / "src" / "02_retrieval"
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_generation))
    sys.path.insert(0, str(_retrieval))
    __package__ = "src.testing.generation.accuracy"

import argparse
import json
import re
import time
import uuid
from collections import defaultdict
from pathlib import Path

from core.db import connect
from clients.embed_client import EmbedClient, DEFAULT_BASE_URL as DEFAULT_EMBED_URL
from clients.llm_client import LLMClient, DEFAULT_BASE_URL as DEFAULT_LLM_URL
from step_01_build_context import build_context
from step_02_chunk_retrieval.retrieve_vector import RetrievedChunk
from step_02_llm_generation import generate_answer
from log.log_generation_accuracy_testing import log_generation_accuracy_testing
from log.log_testing import log_generation_run

_REPO_ROOT = Path(__file__).parents[3]
_SYSTEM_PROMPT = (
    _REPO_ROOT / "system_prompts" / "generation" / "generation.md"
).read_text(encoding="utf-8").strip()

_CATEGORIES = ("fact_single", "summary", "reasoning", "unanswerable")

_JUDGE_SYSTEM_PROMPT, _JUDGE_TEMPLATE = (
    _REPO_ROOT / "system_prompts" / "generation" / "judge.md"
).read_text(encoding="utf-8").split("---", 1)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _parse_judge(response: str) -> tuple[int | None, str | None]:
    score_match = re.search(r"SCORE:\s*([1-5])", response)
    reasoning_match = re.search(r"REASONING:\s*(.+)", response)
    score = int(score_match.group(1)) if score_match else None
    reasoning = reasoning_match.group(1).strip() if reasoning_match else None
    return score, reasoning


def _to_retrieved_chunks(chunks: list[dict]) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=c["chunk_id"],
            source_type=c["source_type"],
            source_id=c["source_id"],
            strategy=c.get("strategy", "plain"),
            voyage_key=c["voyage_key"],
            chunk_index=0,
            text=c.get("text", ""),
            similarity=c.get("similarity", 0.0),
        )
        for c in chunks
        if c.get("text")
    ]


def _print_category_summary(category: str, cosine_sum: float, judge_scores: list[int], total: int) -> None:
    avg_cos = cosine_sum / total if total else 0.0
    avg_judge = sum(judge_scores) / len(judge_scores) if judge_scores else 0.0
    high = sum(1 for s in judge_scores if s >= 4)
    print(f"  {category:<12} n={total:3d} | cosine: {avg_cos:.4f} | judge: {avg_judge:.2f}/5 | ≥4: {high}/{total} ({high/total:.0%})")


def main() -> None:
    p = argparse.ArgumentParser(description="Generation accuracy test")
    p.add_argument("--retrieval-run-id", required=True,
                   help="UUID of the chunk-retrieval run to evaluate (from test_retrieval_chunk_logging)")
    p.add_argument("--embed-url", default=DEFAULT_EMBED_URL,
                   help=f"Embed server base URL (default: {DEFAULT_EMBED_URL})")
    p.add_argument("--llm-url", default=DEFAULT_LLM_URL,
                   help=f"LLM server base URL (default: {DEFAULT_LLM_URL})")
    p.add_argument("--temperature", type=float, default=0.3,
                   help="Generation temperature (default: 0.3)")
    p.add_argument("--max-tokens", type=int, default=2500, dest="max_tokens",
                   help="Generation max tokens (default: 2500)")
    p.add_argument("--limit-per-category", type=int, default=None, dest="limit_per_category",
                   help="Cap rows per category (default: no limit)")
    args = p.parse_args()

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT question_id, question, category, answer, voyage_key, chunks, flags
            FROM (
                SELECT
                    gt.question_id::text AS question_id,
                    trcl.question,
                    trcl.category,
                    gt.answer,
                    gt.voyage_key,
                    trcl.chunks,
                    trcl.flags,
                    ROW_NUMBER() OVER (PARTITION BY trcl.category ORDER BY gt.question_id) AS rn
                FROM test_retrieval_chunk_logging trcl
                JOIN ground_truth gt ON gt.question_id = trcl.question_id
                WHERE trcl.run_id = %s
                  AND trcl.category = ANY(%s)
                  AND (trcl.email_hit = true OR trcl.category = 'unanswerable')
            ) s
            WHERE %s::int IS NULL OR rn <= %s::int
            ORDER BY category, question_id
            """,
            (args.retrieval_run_id, list(_CATEGORIES),
             args.limit_per_category, args.limit_per_category),
        ).fetchall()

    if not rows:
        print(f"No rows found for retrieval_run_id={args.retrieval_run_id}. Has the retrieval test been run?")
        return

    retrieval_flags: dict = rows[0][6] if rows[0][6] else {}
    run_flags = {
        "retrieval_run_id": args.retrieval_run_id,
        "embed_url": args.embed_url,
        "llm_url": args.llm_url,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "limit_per_category": args.limit_per_category,
        "retrieval_flags": retrieval_flags,
    }

    per_cat_counts: dict[str, int] = defaultdict(int)
    for r in rows:
        per_cat_counts[r[2]] += 1
    cat_summary = " | ".join(f"{c}: {per_cat_counts.get(c, 0)}" for c in _CATEGORIES)
    print(f"Questions (hit=true): {len(rows)} | retrieval_run_id: {args.retrieval_run_id}")
    print(f"  per-category: {cat_summary}"
          + (f" | limit_per_category: {args.limit_per_category}" if args.limit_per_category else ""))
    print(f"  llm: {args.llm_url} | embed: {args.embed_url}")

    embed_client = EmbedClient(base_url=args.embed_url)
    llm_client = LLMClient(base_url=args.llm_url)
    run_id = str(uuid.uuid4())

    cat_cosine: dict[str, float] = defaultdict(float)
    cat_judge: dict[str, list[int]] = defaultdict(list)
    cat_total: dict[str, int] = defaultdict(int)

    with connect() as conn:
        for i, (question_id, question, category, ground_truth_answer, voyage_key, chunks_json, _) in enumerate(rows, 1):
            chunks: list[dict] = chunks_json if isinstance(chunks_json, list) else json.loads(chunks_json)
            retrieved = _to_retrieved_chunks(chunks)
            context = build_context(conn, retrieved, [voyage_key])

            t_gen = time.monotonic()
            generated_answer, _, _ = generate_answer(
                llm_client, question, context, _SYSTEM_PROMPT,
                args.temperature, args.max_tokens,
            )
            generation_ms = int((time.monotonic() - t_gen) * 1000)

            gen_emb, gt_emb = embed_client.embed([generated_answer, ground_truth_answer])
            cosine_sim = _cosine_similarity(gen_emb, gt_emb)

            judge_prompt = _JUDGE_TEMPLATE.format(
                question=question,
                ground_truth_answer=ground_truth_answer,
                generated_answer=generated_answer,
            )
            judge_response = llm_client.chat(
                _JUDGE_SYSTEM_PROMPT, judge_prompt, temperature=0, max_tokens=150
            )
            judge_score, judge_reasoning = _parse_judge(judge_response)

            cat_cosine[category] += cosine_sim
            cat_total[category] += 1
            if judge_score is not None:
                cat_judge[category].append(judge_score)

            log_generation_accuracy_testing(
                conn,
                run_id=run_id,
                question_id=question_id,
                generated_answer=generated_answer,
                ground_truth_answer=ground_truth_answer,
                cosine_similarity=cosine_sim,
                judge_score=judge_score,
                judge_reasoning=judge_reasoning,
                generation_ms=generation_ms,
                category=category,
                chunks=chunks,
            )

            if i % 10 == 0:
                total_so_far = sum(cat_total.values())
                all_cosine_so_far = sum(cat_cosine.values()) / total_so_far
                all_scores_so_far = [s for sc in cat_judge.values() for s in sc]
                avg_j = sum(all_scores_so_far) / len(all_scores_so_far) if all_scores_so_far else 0.0
                print(f"  {i}/{len(rows)} — avg cosine: {all_cosine_so_far:.4f} | avg judge: {avg_j:.2f}")

        total_all = sum(cat_total.values())
        all_cosine = sum(cat_cosine.values()) / total_all if total_all else 0.0
        all_scores = [s for sc in cat_judge.values() for s in sc]
        all_judge = sum(all_scores) / len(all_scores) if all_scores else 0.0
        all_high = sum(1 for s in all_scores if s >= 4)

        for cat in _CATEGORIES:
            n = cat_total[cat]
            if n == 0:
                continue
            scores = cat_judge[cat]
            log_generation_run(
                conn,
                run_id=run_id,
                total=n,
                judge_hits=sum(1 for s in scores if s >= 4),
                avg_cosine=cat_cosine[cat] / n,
                avg_judge_score=sum(scores) / len(scores) if scores else 0.0,
                category=cat,
                flags=run_flags,
            )
        log_generation_run(
            conn,
            run_id=run_id,
            total=total_all,
            judge_hits=all_high,
            avg_cosine=all_cosine,
            avg_judge_score=all_judge,
            category="all",
            flags=run_flags,
        )

    print(f"\nDone. run_id={run_id}")
    print("\nPer-category results:")
    for cat in _CATEGORIES:
        n = cat_total[cat]
        if n:
            _print_category_summary(cat, cat_cosine[cat], cat_judge[cat], n)
    print()
    print(f"  {'TOTAL':<12} n={total_all:3d} | cosine: {all_cosine:.4f} | judge: {all_judge:.2f}/5 | ≥4: {all_high}/{total_all} ({all_high/total_all:.0%})")


if __name__ == "__main__":
    main()
