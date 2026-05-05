from __future__ import annotations

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from clients.rerank_client import RerankClient
from step_02_chunk_retrieval.retrieve_chunks import RetrievedChunk


def rerank_chunks(
    client: RerankClient,
    query: str,
    chunks: list[RetrievedChunk],
    top_k: int = 25,
) -> list[RetrievedChunk]:
    """
    Re-scores chunks against query using the cross-encoder reranker and returns
    the top_k by rerank score. Run this on anchor chunks before expansion so only
    the best anchors are expanded.
    """
    if not chunks:
        return []

    scores = client.score(query, [c.text for c in chunks])
    ranked = sorted(zip(scores, chunks), key=lambda x: -x[0])

    return [
        RetrievedChunk(
            chunk_id=c.chunk_id,
            source_type=c.source_type,
            source_id=c.source_id,
            voyage_key=c.voyage_key,
            chunk_index=c.chunk_index,
            text=c.text,
            similarity=score,
        )
        for score, c in ranked[:top_k]
    ]
