"""
Ground truth v3 — strategy-agnostic QA generation for emails and attachments.

For each voyage, sample N chunks (stratified by source_type). For each chunk
pick a random category from the four Know Your RAG classes (fact_single,
summary, reasoning, unanswerable) and generate exactly ONE QA pair using
the category-specific system prompt in system_prompts/ground_truth/.

The generated question must be source-agnostic (no mention of email, pdf,
attachment, etc.). The chunk's source metadata is recorded in the row so
we know where each question originated.

Run from this directory on SPARK:
    python run_build.py
    python run_build.py --target-per-voyage 50 --workers 4
    python run_build.py --voyage-key AFRICAN_JUNIPER_1
    python run_build.py --voyage-key AFRICAN_JUNIPER_1 --target-per-voyage 10

Override env vars:
    LLM_BASE_URL   (default: http://localhost:8002/v1)
    LLM_MODEL      (default: auto-detected)
    DATABASE_URL   (default: postgresql://teamragrats:ragrats@localhost:5433/ragrats)
"""
from __future__ import annotations

import argparse
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[3]))  # repo root for clients/

import psycopg

from clients.llm_client import LLMClient
from config import (
    CATEGORIES,
    DATABASE_URL,
    DEFAULT_TARGET_PER_VOYAGE,
    DEFAULT_WORKERS,
    LLM_BASE_URL,
    LLM_MODEL,
)
from db_writer import insert_qa, next_question_id
from generator import generate_qa
from sampler import (
    ChunkRow,
    list_voyage_keys,
    sample_chunks,
)


def _process_chunk(
    llm: LLMClient,
    chunk: ChunkRow,
    category: str,
) -> dict | None:
    qa = generate_qa(
        llm,
        category=category,
        voyage_key=chunk.voyage_key,
        vessel_name=chunk.vessel_name,
        chunk_text=chunk.text,
    )
    if qa is None:
        return None
    qa["source_type"] = chunk.source_type
    qa["source_id"] = chunk.source_id
    qa["chunk_index"] = chunk.chunk_index
    qa["voyage_key"] = chunk.voyage_key
    qa["vessel_name"] = chunk.vessel_name
    qa["text"] = chunk.text
    return qa


def process_voyage(
    voyage_key: str,
    target: int,
    llm: LLMClient,
    write_conn: psycopg.Connection,
    q_counter: int,
    workers: int,
) -> int:
    read_conn = psycopg.connect(DATABASE_URL)
    chunks = sample_chunks(read_conn, voyage_key, target)
    read_conn.close()

    if not chunks:
        print(f"  [warn] No chunks found for {voyage_key}")
        return 0

    rng = random.Random(hash(voyage_key) & 0xFFFFFFFF)
    pairs = [(c, rng.choice(CATEGORIES)) for c in chunks]

    inserted = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_process_chunk, llm, c, cat): (c, cat) for c, cat in pairs}
        for future in as_completed(futures):
            try:
                qa = future.result()
            except Exception as exc:
                print(f"  [warn] chunk failed: {exc}", file=sys.stderr)
                continue
            if qa is None:
                continue
            question_id = f"gt3_{q_counter:04d}"
            insert_qa(
                write_conn,
                question_id,
                question=qa["question"],
                answer=qa["answer"],
                category=qa["category"],
                text=qa.get("text"),
                source_hint=qa.get("source_hint"),
                source_type=qa["source_type"],
                source_id=qa["source_id"],
                chunk_index=qa["chunk_index"],
                voyage_key=qa["voyage_key"],
                vessel_name=qa["vessel_name"],
            )
            q_counter += 1
            inserted += 1

    return inserted


def main(
    target_per_voyage: int = DEFAULT_TARGET_PER_VOYAGE,
    workers: int = DEFAULT_WORKERS,
    voyage_key_filter: str | None = None,
) -> None:
    llm = LLMClient(base_url=LLM_BASE_URL, model=LLM_MODEL or None)
    print(f"Model: {llm.model} at {llm.base_url}")

    read_conn = psycopg.connect(DATABASE_URL)
    all_keys = list_voyage_keys(read_conn)
    read_conn.close()

    if voyage_key_filter:
        all_keys = [k for k in all_keys if k == voyage_key_filter]
        if not all_keys:
            print(f"No voyage found: {voyage_key_filter}")
            return

    write_conn = psycopg.connect(DATABASE_URL)
    q_counter = next_question_id(write_conn)

    print(
        f"Voyages: {len(all_keys)} | target/voyage: {target_per_voyage} | "
        f"workers: {workers} | starting at gt3_{q_counter:04d}"
    )

    total = 0
    for key in all_keys:
        print(f"\n── {key} ──")
        n = process_voyage(
            voyage_key=key,
            target=target_per_voyage,
            llm=llm,
            write_conn=write_conn,
            q_counter=q_counter,
            workers=workers,
        )
        print(f"  inserted: {n}/{target_per_voyage}")
        q_counter += n
        total += n

    write_conn.close()
    print(f"\nDone. {total} Q&A pairs across {len(all_keys)} voyages.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ground Truth v3 Builder")
    parser.add_argument("--target-per-voyage", type=int, default=DEFAULT_TARGET_PER_VOYAGE)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--voyage-key", type=str, default=None)
    args = parser.parse_args()

    main(
        target_per_voyage=args.target_per_voyage,
        workers=args.workers,
        voyage_key_filter=args.voyage_key,
    )
