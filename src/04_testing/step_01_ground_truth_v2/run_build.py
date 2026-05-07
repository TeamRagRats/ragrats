"""
Ground truth v2 — voyage-anchored, categorised Q&A generation.

Samples chunks per voyage × category, sends each to the local vLLM server,
validates the output, and inserts into ground_truth_v2.

Run on SPARK where both postgres and vLLM are local:
    python run_build.py
    python run_build.py --target-per-voyage 50 --workers 4
    python run_build.py --voyage-key AFRICAN_JUNIPER_1
    python run_build.py --category commercial_terms

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

# Ensure sibling modules are importable when run directly
sys.path.insert(0, str(Path(__file__).parent))

import psycopg

from chunk_sampler import sample_chunks
from config import (
    CATEGORIES,
    CHUNK_BUFFER_MULTIPLIER,
    DATABASE_URL,
    DEFAULT_TARGET_PER_VOYAGE,
    DEFAULT_WORKERS,
    LLM_BASE_URL,
    LLM_MODEL,
)
from db_writer import insert_qa, next_question_id
from llm_client import generate_qa, make_client
from voyage_metadata import VoyageMeta, load_all_voyage_meta


def _target_per_category(target_per_voyage: int, n_categories: int) -> list[int]:
    """Distribute target_per_voyage as evenly as possible over n_categories."""
    base, remainder = divmod(target_per_voyage, n_categories)
    return [base + (1 if i < remainder else 0) for i in range(n_categories)]


def process_voyage_category(
    meta: VoyageMeta,
    category: str,
    target: int,
    client,
    model: str,
    write_conn: psycopg.Connection,
    q_counter_start: int,
    workers: int,
) -> int:
    """Returns number of Q&As inserted for this voyage+category."""
    limit = target * CHUNK_BUFFER_MULTIPLIER
    read_conn = psycopg.connect(DATABASE_URL)
    chunks = sample_chunks(read_conn, meta.voyage_key, limit)
    read_conn.close()

    if not chunks:
        print(f"  [warn] No chunks for {meta.voyage_key} / {category}")
        return 0

    inserted = 0
    q_counter = q_counter_start

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(generate_qa, client, model, meta, chunk, category): chunk
            for chunk in chunks
        }
        for future in as_completed(futures):
            if inserted >= target:
                break
            result = future.result()
            if result:
                question_id = f"gt2_{q_counter:04d}"
                insert_qa(
                    conn=write_conn,
                    question_id=question_id,
                    question=result["question"],
                    answer=result["answer"],
                    category=result["category"],
                    difficulty=result["difficulty"],
                    source_type=result["source_type"],
                    source_id=result["source_id"] or None,
                    source_chunk_id=result["chunk_id"],
                    voyage_key=result["voyage_key"],
                    vessel_name=result["vessel_name"],
                )
                q_counter += 1
                inserted += 1

    return inserted


def main(
    client,
    model: str,
    target_per_voyage: int = DEFAULT_TARGET_PER_VOYAGE,
    workers: int = DEFAULT_WORKERS,
    voyage_key_filter: str | None = None,
    category_filter: str | None = None,
) -> None:
    read_conn = psycopg.connect(DATABASE_URL)
    all_meta = load_all_voyage_meta(read_conn)
    read_conn.close()

    if voyage_key_filter:
        all_meta = [m for m in all_meta if m.voyage_key == voyage_key_filter]
        if not all_meta:
            print(f"No voyage found for key: {voyage_key_filter}")
            return

    categories = [category_filter] if category_filter else CATEGORIES
    targets_per_cat = _target_per_category(target_per_voyage, len(categories))

    write_conn = psycopg.connect(DATABASE_URL)
    q_counter = next_question_id(write_conn)

    total_inserted = 0
    print(
        f"Voyages: {len(all_meta)} | categories: {categories} | "
        f"target/voyage: {target_per_voyage} | workers: {workers} | "
        f"starting at gt2_{q_counter:04d}"
    )

    for meta in all_meta:
        print(f"\n── {meta.voyage_key} ({meta.vessel_name}) ──")
        voyage_inserted = 0

        for category, cat_target in zip(categories, targets_per_cat):
            n = process_voyage_category(
                meta=meta,
                category=category,
                target=cat_target,
                client=client,
                model=model,
                write_conn=write_conn,
                q_counter_start=q_counter,
                workers=workers,
            )
            print(f"  {category}: {n}/{cat_target} inserted")
            q_counter += n
            voyage_inserted += n

        total_inserted += voyage_inserted
        print(f"  Voyage total: {voyage_inserted}/{target_per_voyage}")

    write_conn.close()
    print(f"\nDone. {total_inserted} Q&A pairs inserted across {len(all_meta)} voyages.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-per-voyage", type=int, default=DEFAULT_TARGET_PER_VOYAGE)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--voyage-key", type=str, default=None,
                        help="Run for a single voyage key only")
    parser.add_argument("--category", type=str, default=None,
                        choices=CATEGORIES,
                        help="Run for a single category only")
    args = parser.parse_args()

    client, model = make_client(LLM_BASE_URL, LLM_MODEL)
    main(
        client=client,
        model=model,
        target_per_voyage=args.target_per_voyage,
        workers=args.workers,
        voyage_key_filter=args.voyage_key,
        category_filter=args.category,
    )
