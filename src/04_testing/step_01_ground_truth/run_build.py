"""
Ground truth builder — operator-inspired Q&A grounded in email body + structured_md.

For each voyage_key in `fixtures`, pick 2 emails (earliest-first, body_cleaned > 100
chars), and for each email generate one question per Know Your RAG category
(fact_single, reasoning, summary, unanswerable). Each LLM call is seeded with up
to 8 randomly sampled real operator queries from `operator_queries_v` as style
references.

Run from this directory on SPARK:
    python run_build.py                              # all voyages
    python run_build.py --limit-voyages 5            # first 5 voyages only
    python run_build.py --voyage AFRICAN_JUNIPER_1   # one specific voyage
    python run_build.py --dry-run --limit-voyages 2  # show what would generate

Override env vars:
    LLM_BASE_URL   (default: http://localhost:8002/v1)
    LLM_MODEL      (default: auto-detected)
    DATABASE_URL   (via core.config; default ragrats local)
"""
from __future__ import annotations

import argparse
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
    pick_emails_for_voyage,
    sample_operator_queries,
)


CATEGORIES = ("fact_single", "reasoning", "summary", "unanswerable")
EMAILS_PER_VOYAGE = 2
OPERATOR_QUERY_FEWSHOT = 8


def _process_email(
    llm: LLMClient,
    email: EmailSample,
    vessel_name: str,
    operator_queries: list[str],
) -> list[dict]:
    qas: list[dict] = []
    for category in CATEGORIES:
        qa = generate_qa(
            llm,
            category=category,
            voyage_key=email.voyage_key,
            vessel_name=vessel_name,
            body_cleaned=email.body_cleaned,
            structured_md=email.structured_md or None,
            operator_query_examples=operator_queries,
        )
        if qa is not None:
            qas.append(qa)
    return qas


def process_voyage(
    voyage_key: str,
    llm: LLMClient,
    dry_run: bool = False,
    workers: int = 4,
) -> int:
    with connect() as conn:
        vessel_name = get_vessel_name(conn, voyage_key)
        if not vessel_name:
            print(f"  [warn] no vessel_name in fixtures for {voyage_key}; skipping")
            return 0

        emails = pick_emails_for_voyage(conn, voyage_key, limit=EMAILS_PER_VOYAGE)
        if not emails:
            print(f"  [warn] no eligible emails for {voyage_key}; skipping")
            return 0

        print(
            f"  vessel={vessel_name!r}  emails={len(emails)}  "
            f"attach_chars=[{', '.join(str(len(e.structured_md)) for e in emails)}]"
        )

        per_email_queries = [
            sample_operator_queries(conn, n=OPERATOR_QUERY_FEWSHOT) for _ in emails
        ]

    inserted = 0
    futures_meta: list[tuple] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {}
        for email, queries in zip(emails, per_email_queries):
            fut = pool.submit(_process_email, llm, email, vessel_name, queries)
            futures[fut] = email

        for fut in as_completed(futures):
            email = futures[fut]
            try:
                qas = fut.result()
            except Exception as exc:
                print(f"  [warn] email {email.email_id} failed: {exc}", file=sys.stderr)
                continue

            for qa in qas:
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

    target_per_voyage = EMAILS_PER_VOYAGE * len(CATEGORIES)
    print(
        f"voyages: {len(voyage_keys)} | emails/voyage: {EMAILS_PER_VOYAGE} | "
        f"categories: {len(CATEGORIES)} | target: {target_per_voyage}/voyage | "
        f"workers: {workers} | dry_run: {dry_run}"
    )

    total = 0
    for vk in voyage_keys:
        print(f"\n-- {vk} --")
        n = process_voyage(vk, llm, dry_run=dry_run, workers=workers)
        print(f"  inserted: {n}/{target_per_voyage}")
        total += n

    print(f"\nDone. {total} Q&A pairs across {len(voyage_keys)} voyages.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ground Truth Builder (operator-style)")
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
        limit_voyages=args.limit_voyages,
        voyage_filter=args.voyage,
        dry_run=args.dry_run,
        workers=args.workers,
    )
