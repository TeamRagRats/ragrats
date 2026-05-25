"""Query-embedding cache for the in-process summary+hybrid sweep.

Each question is embedded once per reformulate variant and reused across every
top_k/rerank cell. This mirrors the matrix test's trick of pre-generating all
document embeddings up front: the heavy, repeated work (the embed/LLM round
trips) happens once instead of once per sweep cell.

BM25 text is always the raw question (the pipeline never feeds reformulated text
to the lexical side), so only the vector embedding depends on the reformulate
flag.
"""
from __future__ import annotations

from clients.embed_client import EmbedClient
from clients.llm_client import LLMClient
from step_00_query_reformulation import reformulate_query

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
    llm: LLMClient | None,
    rows_by_category: dict[str, list],
    reformulate_opts: list[bool],
) -> dict[tuple[bool, str], list[float]]:
    """Returns {(reformulate, question_id): embedding} for every needed variant."""
    questions = _all_questions(rows_by_category)
    cache: dict[tuple[bool, str], list[float]] = {}

    for reformulate in reformulate_opts:
        if reformulate:
            if llm is None:
                raise SystemExit("reformulate=True requires an LLM client (server on 8002)")
            print(f"  reformulating {len(questions)} questions ...")
            texts = [reformulate_query(llm, q) for _, q in questions]
        else:
            texts = [q for _, q in questions]
        print(f"  embedding {len(texts)} queries (reformulate={reformulate}) ...")
        embeddings = _embed_batched(client, texts)
        for (question_id, _), emb in zip(questions, embeddings):
            cache[(reformulate, question_id)] = emb
    return cache
