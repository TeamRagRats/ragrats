"""
Ground truth v3 — strategy-agnostic QA generation for emails and attachments.

Samples emails (body_cleaned) and attachment chunks (strategy='plain') per voyage,
generates batched QA pairs via the local vLLM server, and inserts into ground_truth_v3.

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
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[3]))  # repo root for clients/

import psycopg

from clients.llm_client import LLMClient
from config import (
    CHUNK_BUFFER_MULTIPLIER,
    DATABASE_URL,
    DEFAULT_QA_PER_CHUNK,
    DEFAULT_TARGET_PER_VOYAGE,
    DEFAULT_WORKERS,
    LLM_BASE_URL,
    LLM_MODEL,
)
from db_writer import insert_qa, next_question_id
from generator import generate_qa_batch
from sampler import (
    ChunkRow,
    list_voyage_keys,
    sample_chunks,
)


def _process_chunk(
    llm: LLMClient,
    source_type: str,
    source_id: str,
    chunk_index: int | None,
    voyage_key: str,
    vessel_name: str,
    text: str,
    qa_per_chunk: int,
) -> list[dict]:
    results = generate_qa_batch(llm, source_type, voyage_key, vessel_name, text, qa_per_chunk)
    for r in results:
        r["source_type"] = source_type
        r["source_id"] = source_id
        r["chunk_index"] = chunk_index
        r["voyage_key"] = voyage_key
        r["vessel_name"] = vessel_name
    return results


def process_voyage(
    voyage_key: str,
    target: int,
    llm: LLMClient,
    write_conn: psycopg.Connection,
    q_counter: int,
    workers: int,
    qa_per_chunk: int,
) -> int:
    buffer = target * CHUNK_BUFFER_MULTIPLIER

    read_conn = psycopg.connect(DATABASE_URL)
    chunks = sample_chunks(read_conn, voyage_key, buffer)
    read_conn.close()

    if not chunks:
        print(f"  [warn] No chunks found for {voyage_key}")
        return 0

    tasks: list[tuple] = [
        (c.source_type, c.source_id, c.chunk_index, c.voyage_key, c.vessel_name, c.text)
        for c in chunks
    ]

    inserted = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _process_chunk, llm, src_type, src_id, chunk_idx, vk, vn, text, qa_per_chunk
            ): None
            for src_type, src_id, chunk_idx, vk, vn, text in tasks
        }
        for future in as_completed(futures):
            if inserted >= target:
                break
            try:
                results = future.result()
            except Exception as exc:
                print(f"  [warn] chunk failed: {exc}", file=sys.stderr)
                continue

            for r in results:
                if inserted >= target:
                    break
                question_id = f"gt3_{q_counter:04d}"
                insert_qa(
                    write_conn,
                    question_id,
                    question=r["question"],
                    answer=r["answer"],
                    category=r["category"],
                    source_hint=r.get("source_hint"),
                    source_type=r["source_type"],
                    source_id=r["source_id"],
                    chunk_index=r["chunk_index"],
                    voyage_key=r["voyage_key"],
                    vessel_name=r["vessel_name"],
                )
                q_counter += 1
                inserted += 1

    return inserted


def main(
    target_per_voyage: int = DEFAULT_TARGET_PER_VOYAGE,
    workers: int = DEFAULT_WORKERS,
    qa_per_chunk: int = DEFAULT_QA_PER_CHUNK,
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
        f"qa/chunk: {qa_per_chunk} | workers: {workers} | starting at gt3_{q_counter:04d}"
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
            qa_per_chunk=qa_per_chunk,
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
    parser.add_argument("--qa-per-chunk", type=int, default=DEFAULT_QA_PER_CHUNK)
    parser.add_argument("--voyage-key", type=str, default=None)
    args = parser.parse_args()

    main(
        target_per_voyage=args.target_per_voyage,
        workers=args.workers,
        qa_per_chunk=args.qa_per_chunk,
        voyage_key_filter=args.voyage_key,
    )
