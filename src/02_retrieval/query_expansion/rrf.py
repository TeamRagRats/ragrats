from __future__ import annotations

from step_02_chunk_retrieval import RetrievedChunk


def reciprocal_rank_fusion(
    chunk_lists: list[list[RetrievedChunk]],
    top_k: int,
    rrf_k: int = 60,
) -> list[RetrievedChunk]:
    """
    Fuses multiple ranked chunk lists with Reciprocal Rank Fusion.
    Each chunk's RRF score is sum over lists of 1/(rrf_k + rank), where rank is 1-based.
    The chunk's stored similarity is replaced with the fused RRF score so downstream
    code (logging, ordering) can use the same field.
    Returns top_k chunks by fused score.
    """
    scored: dict[str, tuple[RetrievedChunk, float]] = {}
    for chunks in chunk_lists:
        for rank, chunk in enumerate(chunks, start=1):
            contribution = 1.0 / (rrf_k + rank)
            existing = scored.get(chunk.chunk_id)
            if existing is None:
                scored[chunk.chunk_id] = (chunk, contribution)
            else:
                scored[chunk.chunk_id] = (existing[0], existing[1] + contribution)

    fused = [
        RetrievedChunk(
            chunk_id=c.chunk_id,
            source_type=c.source_type,
            source_id=c.source_id,
            voyage_key=c.voyage_key,
            chunk_index=c.chunk_index,
            text=c.text,
            similarity=score,
        )
        for c, score in scored.values()
    ]
    fused.sort(key=lambda c: c.similarity, reverse=True)
    return fused[:top_k]
