from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import psycopg

from clients.embed_client import EmbedClient
from step_01_voyage_key import find_winning_voyage_keys
from step_02_chunk_retrieval import retrieve_chunks, RetrievedChunk
from query_expansion import reciprocal_rank_fusion


def retrieve_multi_query(
    conn: psycopg.Connection,
    embed_client: EmbedClient,
    queries: list[str],
    top_k_1: int,
    top_k_2: int,
    source_types: list[str] | None,
) -> tuple[list[RetrievedChunk], list[str], dict[str, int], int, int]:
    """
    Runs voyage_key selection + chunk retrieval for each query in parallel,
    then fuses the chunk lists with RRF.

    Returns:
        fused_chunks: top_k_2 chunks after RRF
        union_winning_keys: deduplicated voyage_keys across all queries
        union_vote_counts: summed vote counts across queries
        step1_ms, step2_ms: total wall-clock for steps 1 and 2
    """
    embeddings = embed_client.embed(queries)

    def _step1(emb):
        return find_winning_voyage_keys(conn, emb, top_k=top_k_1, source_types=source_types)

    def _step2(emb, keys):
        if not keys:
            return []
        return retrieve_chunks(
            conn, emb, voyage_keys=keys, top_k=top_k_2, source_types=source_types
        )

    t1 = time.monotonic()
    with ThreadPoolExecutor(max_workers=min(8, len(embeddings))) as ex:
        step1_results = list(ex.map(_step1, embeddings))
    step1_ms = int((time.monotonic() - t1) * 1000)

    union_keys: list[str] = []
    seen_keys: set[str] = set()
    union_votes: dict[str, int] = {}
    for keys, votes in step1_results:
        for k in keys:
            if k not in seen_keys:
                seen_keys.add(k)
                union_keys.append(k)
        for k, v in votes.items():
            union_votes[k] = union_votes.get(k, 0) + v

    t2 = time.monotonic()
    with ThreadPoolExecutor(max_workers=min(8, len(embeddings))) as ex:
        chunk_lists = list(
            ex.map(lambda pair: _step2(pair[0], pair[1][0]), zip(embeddings, step1_results))
        )
    step2_ms = int((time.monotonic() - t2) * 1000)

    fused = reciprocal_rank_fusion(chunk_lists, top_k=top_k_2)

    return fused, union_keys, union_votes, step1_ms, step2_ms
