"""
Ground truth generation for RAG evaluation — chunk-based.

Samples chunks from the database stratified by voyage_key × source_type and uses
the local vLLM server to generate realistic Q&A pairs that a charterer or shipping
operations manager would naturally ask. Each row links to the source chunk_id,
enabling precise recall@k evaluation.

Run this ON SPARK where both postgres and vLLM are local:
    python build_ground_truth.py
    python build_ground_truth.py --target 500   # default
    python build_ground_truth.py --workers 8

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
You are a shipping operations expert helping build a question-answer evaluation set.

You will be given a text chunk from a shipping operations system (from an email, \
attachment, or voyage fixture). Decide if the chunk contains a specific, verifiable \
fact worth turning into a ground-truth Q&A pair.

GOOD candidates contain at least one concrete fact:
- Exact quantities, costs, dates, ETAs, speeds, drafts, cargo volumes
- Names of port agents, terminals, surveyors, counterparties
- Document details (B/L numbers, CP dates, contract terms)
- Vessel status events (arrival, departure, NOR tender, engine issues)
- Operational decisions or confirmed instructions

BAD candidates (return has_qa: false):
- Pleasantries or boilerplate with no operational content
- Vague summaries without specific facts
- Content too short or fragmented to form a meaningful question

If the chunk is a GOOD candidate, generate exactly ONE Q&A pair.

CRITICAL RULES FOR THE QUESTION:
1. Write the question as a charterer or shipping operations manager would naturally \
ask it — not as a reading comprehension question about a document.
2. The question MUST be self-contained: use the vessel name, port, company, date, or \
contract reference as it appears in the chunk so the question makes sense without \
knowing the source. NEVER use "the vessel", "the ship", "the cargo", "the port", \
"the charterer" — always replace these with the actual name from the chunk.
3. NEVER use phrases like "the email", "the document", "the chunk", "the text", \
"according to", "mentioned in", "in the attachment" — these make the question unusable.
4. The answer must be directly extractable from the chunk.

GOOD examples:
- "When did MV African Juniper tender NOR at Itaqui?"
- "What daily rate did Weco Bulk propose for attending two vessels simultaneously in October 2025?"
- "What engine fault prevented MV African Juniper from departing anchorage on 1 November 2025?"
- "Who is the port agent for Corio Bay at Buenos Aires?"
- "On what date was MV African Juniper's ATA authorization issued by NABSA?"

BAD examples:
- "What date is mentioned in the text?" — no specific context
- "What did the agent confirm according to the email?" — references the source
- "What was the rate offered?" — which rate? which vessel?
- "On what date was the vessel's ATA authorization issued by NABSA?" — "the vessel" is ambiguous
- "What was the ship's draft on arrival?" — "the ship" is ambiguous
- "When did the cargo loading commence?" — "the cargo" could be any voyage

- question: self-contained question in English a real user would type into the system
- answer: precise answer from the chunk in English (translate if needed)
- difficulty: "easy" (single obvious fact), "medium" (requires careful reading), "hard" (combines multiple facts)

Respond with valid JSON only, no markdown fences:
{"has_qa": true, "question": "...", "answer": "...", "difficulty": "easy|medium|hard"}
or
{"has_qa": false}"""


def make_llm_client() -> tuple[OpenAI, str]:
    client = OpenAI(base_url=LLM_BASE_URL, api_key="none")
    model = os.environ.get("LLM_MODEL") or client.models.list().data[0].id
    print(f"Using model: {model} at {LLM_BASE_URL}")
    return client, model


_GENERIC_PATTERNS = [
    "the vessel",
    "the ship",
    "the cargo",
    "the port",
    "the charterer",
    "the owner",
    "the captain",
    "the document",
    "the email",
    "the attachment",
    "the chunk",
    "the text",
    "according to",
    "mentioned in",
    "in the attachment",
]


def _is_specific_question(question: str) -> bool:
    q = question.lower()
    return not any(pattern in q for pattern in _GENERIC_PATTERNS)


def classify_chunk(
    client: OpenAI,
    model: str,
    chunk_id: str,
    source_type: str,
    source_id: str,
    voyage_key: str,
    text: str,
) -> dict | None:
    snippet = text.strip()[:3000]
    if not snippet:
        return None

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": (
                        f"Voyage: {voyage_key}\n"
                        f"Source type: {source_type}\n\n"
                        f"{snippet}"
                    )},
                ],
                temperature=0.2,
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
                question = result.get("question", "")
                if not _is_specific_question(question):
                    return None
                return {
                    "chunk_id": chunk_id,
                    "source_type": source_type,
                    "source_id": source_id,
                    "voyage_key": voyage_key,
                    "question": question,
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
                print(f"  [warn] chunk {chunk_id}: {exc}", file=sys.stderr)
    return None


def sample_chunks(conn: psycopg.Connection, target: int) -> list[tuple]:
    # Sample up to 10 chunks per (voyage_key, source_type) combo, then shuffle.
    # Multiplier of 3 ensures we have enough candidates to hit the target
    # even at a ~33% pass rate.
    sample_size = target * 3

    rows = conn.execute("""
        WITH ranked AS (
            SELECT
                chunk_id, source_type, source_id, voyage_key, text,
                ROW_NUMBER() OVER (
                    PARTITION BY voyage_key, source_type
                    ORDER BY random()
                ) AS rn
            FROM chunks
        )
        SELECT chunk_id, source_type, source_id, voyage_key, text
        FROM ranked
        WHERE rn <= 10
        ORDER BY random()
        LIMIT %s
    """, (sample_size,)).fetchall()
    return rows


def main(target: int = 500, workers: int = 4) -> None:
    conn = psycopg.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("SELECT question_id FROM ground_truth ORDER BY question_id DESC LIMIT 1")
    row = cur.fetchone()
    last_num = int(row[0].split("_")[1]) if row else 0

    chunks = sample_chunks(conn, target)
    conn.close()

    total = len(chunks)
    print(f"Chunks to process: {total} | workers: {workers} | target: {target} Q&As | starting at qt_{last_num + 1:04d}")

    client, model = make_llm_client()

    q_counter = last_num + 1
    done = 0
    inserted = 0

    print(f"Submitting {total} tasks to {workers} workers...")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(classify_chunk, client, model, *row): row
            for row in chunks
        }
        print(f"All tasks submitted. Waiting for results...")
        write_conn = psycopg.connect(DATABASE_URL)
        write_cur = write_conn.cursor()

        for future in as_completed(futures):
            done += 1
            if done % 10 == 0 or done == 1:
                print(f"  {done}/{total} processed, {inserted} Q&As inserted")

            if inserted >= target:
                continue

            result = future.result()
            if result:
                write_cur.execute("""
                    INSERT INTO ground_truth
                        (question_id, question, ground_truth_answer, difficulty,
                         source_type, source_id, source_chunk_id, voyage_key)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (question_id) DO NOTHING
                """, (
                    f"qt_{q_counter:04d}",
                    result["question"],
                    result["answer"],
                    result["difficulty"],
                    result["source_type"],
                    result["source_id"],
                    result["chunk_id"],
                    result["voyage_key"],
                ))
                write_conn.commit()
                q_counter += 1
                inserted += 1

        write_conn.close()

    print(f"\nDone. {inserted} Q&A pairs inserted from {total} candidate chunks.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=500, help="Target number of Q&A pairs (default: 500)")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers (default: 4)")
    args = parser.parse_args()
    main(target=args.target, workers=args.workers)
