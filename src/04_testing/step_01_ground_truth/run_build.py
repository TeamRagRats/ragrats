"""
Ground truth builder — operator-inspired Q&A grounded in (email body +
randomly chosen attachment's structured_md).

For each voyage_key in `fixtures`:
  1. Sample N*4 distinct emails that:
       - have has_attachment = true
       - have a non-trivial body_cleaned
       - have at least one attachment with non-empty llm_structured.structured_md
     For each chosen email, ONE attachment is picked at random and its
     structured_md is used.
  2. Distribute the four Know Your RAG categories round-robin across the
     sampled emails so each category gets exactly N emails.
  3. Generate one QA pair per (email, attachment) unit using the assigned
     category.

The unique constraint (source_id, category) on the `ground_truth` table
guarantees we never write two questions of the same category for the same
email.

Run from this directory on SPARK:
    python run_build.py                                 # default: per-category = 5
    python run_build.py --per-category 10
    python run_build.py --voyage AFRICAN_JUNIPER_1
    python run_build.py --dry-run --limit-voyages 2

Override env vars:
    LLM_BASE_URL   (default: http://localhost:8002/v1)
    LLM_MODEL      (default: auto-detected)
    DATABASE_URL   (via core.config; default ragrats local)
"""
from __future__ import annotations

import argparse
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[3]))  # repo root for clients/, core/

from clients.llm_client import LLMClient
from core.db import connect
from db_writer import insert_qa
from generator import generate_qa
from sampler import (
    EmailSample,
    list_voyage_keys,
    get_vessel_name,
    pick_emails_with_attachment,
    sample_operator_queries,
)


CATEGORIES = ("fact_single", "reasoning", "summary", "unanswerable")
DEFAULT_PER_CATEGORY = 5
OPERATOR_QUERY_FEWSHOT = 8


def _process_pair(
    llm: LLMClient,
    email: EmailSample,
    category: str,
    vessel_name: str,
    operator_queries: list[str],
) -> dict | None:
    return generate_qa(
        llm,
        category=category,
        voyage_key=email.voyage_key,
        vessel_name=vessel_name,
        body_cleaned=email.body_cleaned,
        structured_md=email.structured_md,
        operator_query_examples=operator_queries,
    )


def _assign_categories(emails: list[EmailSample], per_category: int) -> list[tuple[EmailSample, str]]:
    """Round-robin assign categories so each category gets `per_category` emails
    (or fewer if not enough emails were sampled)."""
    pairs: list[tuple[EmailSample, str]] = []
    rng = random.Random(hash(tuple(e.email_id for e in emails)) & 0xFFFFFFFF)
    shuffled = emails[:]
    rng.shuffle(shuffled)
    for idx, email in enumerate(shuffled):
        category = CATEGORIES[idx // per_category % len(CATEGORIES)]
        pairs.append((email, category))
        if len(pairs) >= per_category * len(CATEGORIES):
            break
    return pairs


def process_voyage(
    voyage_key: str,
    per_category: int,
    llm: LLMClient,
    dry_run: bool = False,
    workers: int = 4,
) -> int:
    target = per_category * len(CATEGORIES)
    with connect() as conn:
        vessel_name = get_vessel_name(conn, voyage_key)
        if not vessel_name:
            print(f"  [warn] no vessel_name in fixtures for {voyage_key}; skipping")
            return 0

        emails = pick_emails_with_attachment(conn, voyage_key, limit=target)
        if not emails:
            print(f"  [warn] no eligible emails-with-attachment for {voyage_key}; skipping")
            return 0

        operator_queries = sample_operator_queries(conn, n=OPERATOR_QUERY_FEWSHOT)

    print(
        f"  vessel={vessel_name!r}  sampled={len(emails)}/{target}  "
        f"per_category={per_category}"
    )

    pairs = _assign_categories(emails, per_category)

    inserted = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _process_pair, llm, email, category, vessel_name, operator_queries
            ): (email, category)
            for email, category in pairs
        }

        for fut in as_completed(futures):
            email, category = futures[fut]
            try:
                qa = fut.result()
            except Exception as exc:
                print(f"  [warn] email {email.email_id} ({category}) failed: {exc}", file=sys.stderr)
                continue
            if qa is None:
                continue

            if dry_run:
                print(
                    f"    [dry-run] {qa['category']:12s}  "
                    f"Q: {qa['question'][:100]}\n"
                    f"                 A: {qa['answer'][:100]}"
                )
                inserted += 1
                continue

            with connect() as wconn:
                ok = insert_qa(
                    wconn,
                    question=qa["question"],
                    answer=qa["answer"],
                    category=qa["category"],
                    body_cleaned=email.body_cleaned,
                    structured_md=email.structured_md,
                    thread_id=email.thread_id,
                    source_id=email.email_id,
                    voyage_key=email.voyage_key,
                )
            if ok:
                inserted += 1

    return inserted


def main(
    per_category: int = DEFAULT_PER_CATEGORY,
    limit_voyages: int | None = None,
    voyage_filter: str | None = None,
    dry_run: bool = False,
    workers: int = 4,
) -> None:
    llm = LLMClient()
    print(f"Model: {llm.model} at {llm.base_url}")

    with connect() as conn:
        voyage_keys = list_voyage_keys(conn, limit=limit_voyages)

    if voyage_filter:
        voyage_keys = [v for v in voyage_keys if v == voyage_filter]
        if not voyage_keys:
            print(f"No voyage matches: {voyage_filter}")
            return

    target_per_voyage = per_category * len(CATEGORIES)
    print(
        f"voyages: {len(voyage_keys)} | per_category: {per_category} | "
        f"categories: {len(CATEGORIES)} | target: {target_per_voyage}/voyage | "
        f"workers: {workers} | dry_run: {dry_run}"
    )

    total = 0
    for vk in voyage_keys:
        print(f"\n-- {vk} --")
        n = process_voyage(
            voyage_key=vk,
            per_category=per_category,
            llm=llm,
            dry_run=dry_run,
            workers=workers,
        )
        print(f"  inserted: {n}/{target_per_voyage}")
        total += n

    print(f"\nDone. {total} Q&A pairs across {len(voyage_keys)} voyages.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ground Truth Builder (email + 1 attachment)")
    parser.add_argument("--per-category", type=int, default=DEFAULT_PER_CATEGORY,
                        help=f"Emails (= QAs) per category per voyage. Default {DEFAULT_PER_CATEGORY}.")
    parser.add_argument("--limit-voyages", type=int, default=None,
                        help="Process only the first N voyages (sorted by voyage_key).")
    parser.add_argument("--voyage", type=str, default=None,
                        help="Process a single specific voyage_key.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate and print Q&A but do not write to DB.")
    parser.add_argument("--workers", type=int, default=4,
                        help="Concurrent LLM calls per voyage.")
    args = parser.parse_args()

    main(
        per_category=args.per_category,
        limit_voyages=args.limit_voyages,
        voyage_filter=args.voyage,
        dry_run=args.dry_run,
        workers=args.workers,
    )
