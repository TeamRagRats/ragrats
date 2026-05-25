"""Query-embedding cache for the in-process summary+hybrid sweep.

Each question is embedded once per reformulate variant and reused across every
top_k/rerank cell. This mirrors the matrix test's trick of pre-generating all
document embeddings up front: the heavy, repeated embed work happens once
instead of once per sweep cell.

Reformulated text is read from ground_truth.question_reformulated (populated up
front by step_00_query_reformulation/populate_ground_truth.py), so the sweep
never calls the LLM itself.

BM25 text is always the raw question (the pipeline never feeds reformulated text
to the lexical side), so only the vector embedding depends on the reformulate
flag.
"""
from __future__ import annotations

from clients.embed_client import EmbedClient

_EMBED_BATCH = 128


def _all_questions(rows_by_category: dict[str, list]) -> list[tuple]:
    """Flatten to (question_id, question) across all categories."""
    out: list[tuple] = []
    for rows in rows_by_category.values():
        for question_id, question, *_ in rows:
            out.append((question_id, question))
    return out


def _embed_batched(client: EmbedClient, texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for start in range(0, len(texts), _EMBED_BATCH):
        out.extend(client.embed(texts[start:start + _EMBED_BATCH]))
    return out


def build_query_embedding_cache(
    client: EmbedClient,
    reformulated_by_id: dict[str, str],
    rows_by_category: dict[str, list],
    reformulate_opts: list[bool],
) -> dict[tuple[bool, str], list[float]]:
    """Returns {(reformulate, question_id): embedding} for every needed variant.

    reformulated_by_id maps question_id -> stored reformulation (from
    ground_truth.question_reformulated). When reformulate=True is swept, every
    question must have an entry; a missing one means populate_ground_truth.py
    has not been run (or not with --force after a prompt change)."""
    questions = _all_questions(rows_by_category)
    cache: dict[tuple[bool, str], list[float]] = {}

    for reformulate in reformulate_opts:
        if reformulate:
            missing = [qid for qid, _ in questions if qid not in reformulated_by_id]
            if missing:
                raise SystemExit(
                    f"reformulate=True needs ground_truth.question_reformulated for "
                    f"all questions, but {len(missing)} are missing. Run "
                    "step_00_query_reformulation/populate_ground_truth.py first."
                )
            texts = [reformulated_by_id[qid] for qid, _ in questions]
        else:
            texts = [q for _, q in questions]
        print(f"  embedding {len(texts)} queries (reformulate={reformulate}) ...")
        embeddings = _embed_batched(client, texts)
        for (question_id, _), emb in zip(questions, embeddings):
            cache[(reformulate, question_id)] = emb
    return cache
