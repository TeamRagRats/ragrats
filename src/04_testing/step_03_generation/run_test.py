"""
Generation accuracy test (retrieval bypassed).

For every ground_truth row, feeds the known correct chunk directly to
build_context + generate_answer, then scores the output against
ground_truth_answer using:
  - cosine similarity between embeddings (objective baseline)
  - LLM-as-judge 1-5 score (qualitative signal, same-model bias acknowledged)

Run on SPARK where both postgres, the embed server, and the LLM are reachable:
    python run_test.py
    python run_test.py --embed-url http://localhost:8003/v1
    python run_test.py --llm-url http://localhost:8002/v1
"""

from __future__ import annotations

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _repo_root = _here.parents[2]
    _generation = _repo_root / "src" / "03_generation"
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_generation))
    __package__ = "src.testing.generation.accuracy"

import argparse
import re
import time
import uuid
from pathlib import Path

from core.db import connect
from clients.embed_client import EmbedClient, DEFAULT_BASE_URL as DEFAULT_EMBED_URL
from clients.llm_client import LLMClient, DEFAULT_BASE_URL as DEFAULT_LLM_URL
from step_01_context_builder import build_context
from step_02_llm_generation import generate_answer
from log.log_generation_accuracy_testing import log_generation_accuracy_testing
from log.log_testing import log_generation_run

_REPO_ROOT = Path(__file__).parents[4]
_SYSTEM_PROMPT = (
    _REPO_ROOT / "system_prompts" / "generation" / "generation.md"
).read_text(encoding="utf-8").strip()

_JUDGE_SYSTEM_PROMPT = (
    "You are an expert evaluator assessing the quality of a RAG system's generated answer "
    "compared to a reference answer. Be strict and objective."
)

_JUDGE_TEMPLATE = """\
Question: {question}

Reference answer: {ground_truth_answer}

Generated answer: {generated_answer}

Score the generated answer 1-5:
1 = Wrong or completely off-topic
2 = Partially correct but missing key information
3 = Mostly correct with minor gaps
4 = Correct and complete
5 = Correct, complete, and well-formulated

Respond with exactly:
SCORE: <number>
REASONING: <one sentence>\
"""


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


def main() -> None:
    p = argparse.ArgumentParser(description="Generation accuracy test")
    p.add_argument("--embed-url", default=DEFAULT_EMBED_URL,
                   help=f"Embed server base URL (default: {DEFAULT_EMBED_URL})")
    p.add_argument("--llm-url", default=DEFAULT_LLM_URL,
                   help=f"LLM server base URL (default: {DEFAULT_LLM_URL})")
    p.add_argument("--temperature", type=float, default=0.3,
                   help="Generation temperature (default: 0.3)")
    p.add_argument("--max-tokens", type=int, default=2500, dest="max_tokens",
                   help="Generation max tokens (default: 2500)")
    args = p.parse_args()

    with connect() as conn:
        rows = conn.execute("""
            SELECT gt.question_id, gt.question, gt.ground_truth_answer,
                   c.chunk_id::text, c.voyage_key, c.source_type, c.source_id,
                   c.chunk_index, c.text
            FROM ground_truth gt
            JOIN chunks c ON c.chunk_id = gt.source_chunk_id
            WHERE gt.source_chunk_id IS NOT NULL
            ORDER BY gt.question_id
        """).fetchall()

    if not rows:
        print("No ground_truth rows with source_chunk_id found.")
        return

    print(f"Questions: {len(rows)} | embed: {args.embed_url} | llm: {args.llm_url}")

    embed_client = EmbedClient(base_url=args.embed_url)
    llm_client = LLMClient(base_url=args.llm_url)
    run_id = str(uuid.uuid4())

    cosine_sum = 0.0
    judge_scores: list[int] = []

    with connect() as conn:
        for i, (question_id, question, ground_truth_answer,
                chunk_id, voyage_key, source_type, source_id,
                chunk_index, chunk_text) in enumerate(rows, 1):

            context = build_context([{
                "chunk_id": chunk_id,
                "voyage_key": voyage_key,
                "source_type": source_type,
                "source_id": source_id,
                "chunk_index": chunk_index,
                "similarity": 1.0,
                "text": chunk_text,
            }])

            t_gen = time.monotonic()
            generated_answer, _ = generate_answer(
                llm_client, question, context, _SYSTEM_PROMPT,
                args.temperature, args.max_tokens,
            )
            generation_ms = int((time.monotonic() - t_gen) * 1000)

            gen_emb, gt_emb = embed_client.embed([generated_answer, ground_truth_answer])
            cosine_sim = _cosine_similarity(gen_emb, gt_emb)
            cosine_sum += cosine_sim

            judge_prompt = _JUDGE_TEMPLATE.format(
                question=question,
                ground_truth_answer=ground_truth_answer,
                generated_answer=generated_answer,
            )
            judge_response = llm_client.chat(
                _JUDGE_SYSTEM_PROMPT, judge_prompt, temperature=0, max_tokens=150
            )
            judge_score, judge_reasoning = _parse_judge(judge_response)
            if judge_score is not None:
                judge_scores.append(judge_score)

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
            )

            if i % 10 == 0:
                avg_cos = cosine_sum / i
                avg_judge = sum(judge_scores) / len(judge_scores) if judge_scores else 0.0
                print(f"  {i}/{len(rows)} — avg cosine: {avg_cos:.4f} | avg judge: {avg_judge:.2f}")

    total = len(rows)
    avg_cosine = cosine_sum / total if total else 0.0
    avg_judge = sum(judge_scores) / len(judge_scores) if judge_scores else 0.0
    high_quality = sum(1 for s in judge_scores if s >= 4)

    with connect() as conn:
        log_generation_run(
            conn,
            run_id=run_id,
            total=total,
            judge_hits=high_quality,
            avg_cosine=avg_cosine,
            avg_judge_score=avg_judge,
        )

    print(f"\nDone. run_id={run_id}")
    print(f"Avg cosine similarity: {avg_cosine:.4f}")
    print(f"Avg judge score:       {avg_judge:.2f}/5")
    print(f"Judge score >= 4:      {high_quality}/{total} ({high_quality/total:.1%})")


if __name__ == "__main__":
    main()
