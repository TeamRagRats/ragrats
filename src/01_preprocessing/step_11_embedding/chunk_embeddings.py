from __future__ import annotations

import gc
import logging

import psycopg
import psycopg.sql

from shared.logging.run_logger import step
from clients.embed_client import EmbedClient

BATCH_SIZE = 32


def get_pending(conn: psycopg.Connection, limit: int | None = None) -> list[dict]:
    sql = """
        SELECT chunk_id, text
        FROM chunks
        WHERE embedding IS NULL
        ORDER BY chunk_id
    """
    with conn.cursor() as cur:
        if limit is not None:
            cur.execute(psycopg.sql.SQL(sql + " LIMIT %s"), (limit,))
        else:
            cur.execute(psycopg.sql.SQL(sql))
        rows = cur.fetchall()
    cols = ["chunk_id", "text"]
    return [dict(zip(cols, row)) for row in rows]


def _upsert_batch(conn: psycopg.Connection, results: list[dict]) -> None:
    sql = """
        UPDATE chunks
        SET embedding = %s::halfvec,
            model     = %s
        WHERE chunk_id = %s
    """
    with conn.cursor() as cur:
        cur.executemany(sql, [
            (r["embedding"], r["model"], r["chunk_id"])
            for r in results
        ])
    conn.commit()


def _cleanup_memory(logger: logging.Logger) -> None:
    collected = gc.collect()
    logger.debug(f"GC collected {collected} objects")
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def run(
    conn: psycopg.Connection,
    run_id,
    client: EmbedClient,
    limit: int | None = None,
    logger: logging.Logger | None = None,
    batch_size: int = BATCH_SIZE,
) -> int:
    if logger is None:
        logger = logging.getLogger("chunk_embeddings")

    with step(conn, run_id, "chunk_embeddings"):
        pending = get_pending(conn, limit)
        total = len(pending)
        n_batches = (total + batch_size - 1) // batch_size
        logger.info(f"[embed] {total} chunk(s) | batch={batch_size} | {n_batches} batches")

        done = 0
        errors = 0

        for batch_idx in range(n_batches):
            batch = pending[batch_idx * batch_size:(batch_idx + 1) * batch_size]
            texts = [row["text"] for row in batch]

            try:
                vectors = client.embed(texts)
            except Exception as exc:
                logger.error(f"  [embed batch {batch_idx + 1}/{n_batches}] FAILED: {exc}")
                errors += len(batch)
                continue

            results = [
                {"chunk_id": row["chunk_id"], "embedding": vector, "model": client.model}
                for row, vector in zip(batch, vectors)
            ]
            _upsert_batch(conn, results)
            done += len(results)
            logger.info(f"  [embed batch {batch_idx + 1}/{n_batches}] {len(results)} OK | total {done}/{total}")

            _cleanup_memory(logger)

        logger.info(f"[embed] Færdig: {done}/{total} embeddings genereret. Fejl: {errors}")
        return done
