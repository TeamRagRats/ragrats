from __future__ import annotations

# Builds a temporary_chunks table for retrieval testing.
# Pulls 25 summaries × 4 voyage_keys (= 100 rows) from each of the 4 summary tables,
# embeds them, and writes them into temporary_chunks (same schema as chunks).
# Drops and recreates the table on every run.
# Run: python -m src.preprocessing.run_build_temporary_chunks

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent
    _repo_root = _here.parents[1]
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_here))
    __package__ = "src.preprocessing"

import os
import sys
import time
import logging

from shared.db import connect
from step_11_embedding.embed_client import EmbedClient, wait_for_server, DEFAULT_BASE_URL

VOYAGES_PER_SOURCE = 4
ROWS_PER_VOYAGE = 25
BATCH_SIZE = 32

SOURCES = [
    {
        "table": "email_attach_summaries",
        "source_type": "email_attach",
        "source_id_expr": "email_id::text",
        "voyage_col": "voyage_key",
    },
    {
        "table": "thread_summaries",
        "source_type": "thread",
        "source_id_expr": "thread_id::text",
        "voyage_col": "voyage_key",
    },
    {
        "table": "fixture_summaries",
        "source_type": "fixture",
        "source_id_expr": "voyage_key",
        "voyage_col": "voyage_key",
    },
    {
        "table": "phase_summaries",
        "source_type": "phase",
        "source_id_expr": "voyage_key || ':' || phase_index::text",
        "voyage_col": "voyage_key",
    },
]


def _setup_table(conn) -> None:
    conn.execute("DROP TABLE IF EXISTS temporary_chunks CASCADE")
    conn.execute("""
        CREATE TABLE temporary_chunks (
            chunk_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_type TEXT NOT NULL,
            source_id   TEXT NOT NULL,
            voyage_key  TEXT NOT NULL,
            chunk_index INTEGER NOT NULL DEFAULT 0,
            text        TEXT NOT NULL,
            embedding   halfvec(2560),
            char_count  INTEGER,
            model       TEXT,
            UNIQUE (source_type, source_id, chunk_index)
        )
    """)
    conn.commit()


def _get_voyage_keys(conn, table: str, voyage_col: str) -> list[str]:
    rows = conn.execute(
        f"SELECT DISTINCT {voyage_col} FROM {table} WHERE status = 'ok' LIMIT %s",
        (VOYAGES_PER_SOURCE,),
    ).fetchall()
    return [r[0] for r in rows]


def _fetch_rows(conn, source: dict, voyage_key: str) -> list[dict]:
    table = source["table"]
    sid_expr = source["source_id_expr"]
    vcol = source["voyage_col"]
    rows = conn.execute(
        f"""
        SELECT summary, {vcol}, {sid_expr} AS source_id
        FROM {table}
        WHERE {vcol} = %s AND status = 'ok'
        ORDER BY random()
        LIMIT %s
        """,
        (voyage_key, ROWS_PER_VOYAGE),
    ).fetchall()
    return [{"text": r[0], "voyage_key": r[1], "source_id": r[2]} for r in rows]


def _embed_and_insert(
    conn, source_type: str, rows: list[dict], client: EmbedClient, logger: logging.Logger
) -> int:
    inserted = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        texts = [r["text"] for r in batch]
        vectors = client.embed(texts)
        for row, vec in zip(batch, vectors):
            conn.execute(
                """
                INSERT INTO temporary_chunks
                    (source_type, source_id, voyage_key, chunk_index, text, embedding, char_count, model)
                VALUES (%s, %s, %s, 0, %s, %s::halfvec, %s, %s)
                ON CONFLICT (source_type, source_id, chunk_index) DO NOTHING
                """,
                (
                    source_type,
                    str(row["source_id"]),
                    row["voyage_key"],
                    row["text"],
                    vec,
                    len(row["text"]),
                    client.model,
                ),
            )
            inserted += 1
        conn.commit()
        logger.info(f"  Embedded batch {i // BATCH_SIZE + 1} ({len(batch)} rows)")
    return inserted


def _create_index(conn, logger: logging.Logger) -> None:
    logger.info("Creating HNSW index on temporary_chunks.embedding ...")
    conn.execute("""
        CREATE INDEX temporary_chunks_embedding_hnsw_idx
        ON temporary_chunks USING hnsw (embedding halfvec_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)
    conn.commit()
    logger.info("HNSW index created.")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("build_temporary_chunks")

    base_url = os.environ.get("EMBED_BASE_URL", DEFAULT_BASE_URL)
    logger.info(f"Waiting for embed server: {base_url} ...")
    if not wait_for_server(base_url, timeout_s=120):
        logger.error(f"Embed server not available: {base_url}")
        sys.exit(1)

    client = EmbedClient(base_url=base_url)
    logger.info(f"Model: {client.model}")

    t0 = time.monotonic()
    total = 0

    with connect() as conn:
        logger.info("Setting up temporary_chunks table ...")
        _setup_table(conn)

        for source in SOURCES:
            source_type = source["source_type"]
            logger.info(f"\n--- {source['table']} (source_type='{source_type}') ---")

            voyage_keys = _get_voyage_keys(conn, source["table"], source["voyage_col"])
            if not voyage_keys:
                logger.warning("  No voyage_keys with status='ok' found — skipping.")
                continue
            logger.info(f"  voyage_keys selected: {voyage_keys}")

            all_rows: list[dict] = []
            for vk in voyage_keys:
                rows = _fetch_rows(conn, source, vk)
                logger.info(f"  {vk}: {len(rows)} rows fetched")
                all_rows.extend(rows)

            n = _embed_and_insert(conn, source_type, all_rows, client, logger)
            logger.info(f"  Inserted {n} rows for {source_type}")
            total += n

        _create_index(conn, logger)

    logger.info(f"\nDone. Total rows inserted: {total} | Wall-time: {time.monotonic() - t0:.1f}s")


if __name__ == "__main__":
    main()
