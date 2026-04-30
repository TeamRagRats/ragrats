"""
Ground truth generation for RAG evaluation.

Queries all emails with question marks from the DB, uses the local vLLM server
(same one used by the pipeline) to filter noise and extract one factual Q&A pair
per email. Results are written directly to the ground_truth table in postgres.
Free — no Anthropic API credits needed.

Run this ON SPARK where both postgres and vLLM are local:
    python build_ground_truth.py
    python build_ground_truth.py --limit 100   # test run
    python build_ground_truth.py --workers 8   # more parallelism

Override defaults via env vars:
    LLM_BASE_URL   (default: http://localhost:8002/v1)
    LLM_MODEL      (default: auto-detected from server)
    DATABASE_URL   (default: postgresql://teamragrats:ragrats@localhost:5433/ragrats)
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg
from openai import OpenAI

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://teamragrats:ragrats@localhost:5433/ragrats",
)
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:8002/v1")

SYSTEM_PROMPT = """\
You are an expert at analyzing shipping operations emails (bulk carrier voyages).

Given an email, decide if it contains a CLEAR FACTUAL DETAIL worth adding to a \
ground-truth Q&A set for a RAG system that answers questions about shipping voyages.

A GOOD candidate email contains at least one specific, verifiable fact such as:
- Exact quantities, costs, dates, ETAs, speeds, drafts, cargo volumes
- Names of port agents, terminals, surveyors, counterparties
- Document details (B/L numbers, CP dates, LOI terms)
- Vessel status events (arrival, departure, NOR tender, engine issues)
- Instructions or confirmations about specific operational matters

BAD candidates (return has_qa: false):
- Pure social pleasantries with no operational content ("How are you?", "Tudo bem?")
- Generic auto-replies, out-of-office messages, or delivery confirmations
- Emails with only vague requests and no specific facts
- Boilerplate footers or disclaimers

If the email is a GOOD candidate, generate exactly ONE factual Q&A pair:
- question: a specific question a user would ask the RAG system (in English)
- answer: the precise answer from this email (in English; translate if needed)
- difficulty: "easy" (single obvious fact), "medium" (read carefully), or "hard" (combine facts)

Respond with valid JSON only, no markdown fences:
{"has_qa": true, "question": "...", "answer": "...", "difficulty": "easy|medium|hard"}
or
{"has_qa": false}"""


def make_llm_client() -> tuple[OpenAI, str]:
    client = OpenAI(base_url=LLM_BASE_URL, api_key="none")
    model = os.environ.get("LLM_MODEL") or client.models.list().data[0].id
    print(f"Using model: {model} at {LLM_BASE_URL}")
    return client, model


def classify_email(
    client: OpenAI,
    model: str,
    email_id,
    thread_id,
    voyage_key: str,
    sent_at,
    eml_path: str,
    body_cleaned: str,
) -> dict | None:
    body_snippet = (body_cleaned or "").strip()[:3000]
    if not body_snippet:
        return None

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": (
                        f"Voyage: {voyage_key}\n"
                        f"Date: {str(sent_at)[:10] if sent_at else 'unknown'}\n\n"
                        f"{body_snippet}"
                    )},
                ],
                temperature=0.1,
                max_tokens=400,
                extra_body={
                    "chat_template_kwargs": {"enable_thinking": False},
                    "repetition_penalty": 1.15,
                },
                timeout=60,
            )
            raw = (response.choices[0].message.content or "").strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.rsplit("```", 1)[0]
            result = json.loads(raw)
            if result.get("has_qa"):
                return {
                    "email_id": str(email_id),
                    "thread_id": str(thread_id) if thread_id else None,
                    "voyage_key": voyage_key,
                    "sent_at": str(sent_at)[:10] if sent_at else None,
                    "eml_path": eml_path or None,
                    "question": result.get("question", ""),
                    "answer": result.get("answer", ""),
                    "difficulty": result.get("difficulty", "medium"),
                }
            return None
        except json.JSONDecodeError:
            pass
        except Exception as exc:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
            else:
                print(f"  [warn] {email_id}: {exc}", file=sys.stderr)
    return None


def main(limit: int | None = None, workers: int = 4) -> None:
    conn = psycopg.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""
        SELECT email_id, thread_id, voyage_key, sent_at, eml_path, body_cleaned
        FROM emails
        WHERE body_cleaned LIKE '%?%'
          AND body_cleaned IS NOT NULL
        ORDER BY voyage_key, sent_at
    """)
    emails = cur.fetchall()

    # Find highest existing question_id to continue numbering
    cur.execute("SELECT question_id FROM ground_truth ORDER BY question_id DESC LIMIT 1")
    row = cur.fetchone()
    if row:
        last_num = int(row[0].split("_")[1])
    else:
        last_num = 0
    conn.close()

    if limit:
        emails = emails[:limit]

    total = len(emails)
    print(f"Emails to process: {total} | workers: {workers} | starting at qt_{last_num + 1:04d}")

    client, model = make_llm_client()

    q_counter = last_num + 1
    done = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(classify_email, client, model, *row): row
            for row in emails
        }
        write_conn = psycopg.connect(DATABASE_URL)
        write_cur = write_conn.cursor()

        for future in as_completed(futures):
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{total} processed, {q_counter - last_num - 1} Q&As so far")
            result = future.result()
            if result:
                write_cur.execute("""
                    INSERT INTO ground_truth
                        (question_id, question, ground_truth_answer, difficulty,
                         source_email_id, thread_id, voyage_key, voyage_path, email_time)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (question_id) DO NOTHING
                """, (
                    f"qt_{q_counter:04d}",
                    result["question"],
                    result["answer"],
                    result["difficulty"],
                    result["email_id"],
                    result["thread_id"],
                    result["voyage_key"],
                    result["eml_path"],
                    result["sent_at"],
                ))
                write_conn.commit()
                q_counter += 1

        write_conn.close()

    found = q_counter - last_num - 1
    print(f"\nDone. {found} Q&A pairs inserted from {total} candidate emails.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Process only N emails (for testing)")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers (default: 4)")
    args = parser.parse_args()
    main(limit=args.limit, workers=args.workers)
