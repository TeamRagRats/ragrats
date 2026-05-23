from __future__ import annotations

from .retrieve_vector import RetrievedChunk


def rrf_fuse(
    vector_results: list[RetrievedChunk],
    lexical_results: list[RetrievedChunk],
    top_k: int,
    rrf_k: int = 60,
) -> list[RetrievedChunk]:
    """Reciprocal Rank Fusion: score = sum_over_lists(1 / (rrf_k + rank)).

    Identity is chunk_id. When a chunk appears in both lists, we keep the
    RetrievedChunk instance from the vector list (it carries cosine
    similarity, which is what `expand_chunks` and downstream loggers expect
    to see). The fused score itself is not propagated — RRF scores aren't
    comparable to cosine similarity.

    `lexical_results` may come from either the tsrank or bm25 retriever;
    fusion is identical for both.
    """
    fused: dict[str, float] = {}
    objects: dict[str, RetrievedChunk] = {}

    for rank, chunk in enumerate(vector_results, 1):
        fused[chunk.chunk_id] = fused.get(chunk.chunk_id, 0.0) + 1.0 / (rrf_k + rank)
        objects.setdefault(chunk.chunk_id, chunk)

    for rank, chunk in enumerate(lexical_results, 1):
        fused[chunk.chunk_id] = fused.get(chunk.chunk_id, 0.0) + 1.0 / (rrf_k + rank)
        objects.setdefault(chunk.chunk_id, chunk)

    ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    return [objects[chunk_id] for chunk_id, _ in ordered[:top_k]]
