"""
Investigative ground truth generation for RAG evaluation.

Generates realistic business questions a charterer or operations manager
would actually type — questions about patterns, issues, and decisions
across a voyage or thread, not extractable single facts.

Sources:
  - phase_summaries: all phases for a voyage_key are concatenated in order
  - thread_summaries: each thread summary is used individually

Run on SPARK where both postgres and vLLM are local:
    python build_ground_truth_investigative.py
    python build_ground_truth_investigative.py --target 200
    python build_ground_truth_investigative.py --source phases
    python build_ground_truth_investigative.py --source threads
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

You will be given a summary of a voyage (multiple phases) or an email thread from a \
shipping operations system. Generate ONE realistic question that a charterer or \
shipping operations manager would actually type into a search system.

GOOD questions are investigative and business-driven:
- About problems, delays, disputes, or incidents that occurred
- About decisions made or instructions given
- About costs, responsibilities, or contract terms discussed
- About the history or outcome of a specific situation

CRITICAL RULES:
1. The question must sound like something a real person types — not a quiz question \
about a document.
2. Always use the actual vessel name, port name, or company name from the text. \
NEVER use "the vessel", "the ship", "the cargo", "the port", "the charterer".
3. Do NOT ask about real-time or current state — only about events and facts from \
the text.
4. Do NOT reference the source ("according to the email", "in the summary", etc.).
5. The question should require reading ACROSS the full context to answer — not just \
extracting one specific number or date.

GOOD examples:
- "Did MV African Juniper experience any delays at Itaqui during her last call?"
- "Were there any disputes about laytime or demurrage on voyage AFGJUN-2025-03?"
- "What problems did African Juniper 1 encounter during loading at Santos?"
- "Have we had any issues with the port agent at Buenos Aires on recent voyages?"
- "How was the survey cost dispute between owners and charterers resolved on the \
Cape Condor fixture?"

BAD examples:
- "What date is mentioned?" — extractive, not investigative
- "What was the vessel's ETA?" — too specific, extractive
- "What does the email say about costs?" — references the source
- "What is the ship currently doing?" — real-time state

Respond with valid JSON only, no markdown fences:
{"has_qa": true, "question": "...", "answer": "...", "difficulty": "easy|medium|hard"}
or
{"has_qa": false}"""

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
    "currently",
]


def _is_specific_question(question: str) -> bool:
    q = question.lower()
    return not any(pattern in q for pattern in _GENERIC_PATTERNS)


def make_llm_client() -> tuple[OpenAI, str]:
    client = OpenAI(base_url=LLM_BASE_URL, api_key="none")
    model = os.environ.get("LLM_MODEL") or client.models.list().data[0].id
    print(f"Using model: {model} at {LLM_BASE_URL}")
    return client, model


def generate_question(
    client: OpenAI,
    model: str,
    source_type: str,
    source_id: str,
    voyage_key: str,
    text: str,
) -> dict | None:
    snippet = text.strip()[:4000]
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
                temperature=0.4,
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
                print(f"  [warn] {source_type} {source_id}: {exc}", file=sys.stderr)
    return None


def load_phase_sources(conn: psycopg.Connection) -> list[tuple]:
    """One entry per voyage_key — all phase summaries concatenated in order."""
    rows = conn.execute("""
        SELECT voyage_key, STRING_AGG(summary, E'\n\n' ORDER BY phase_index) AS text
        FROM phase_summaries
        WHERE summary IS NOT NULL AND summary <> ''
        GROUP BY voyage_key
        HAVING COUNT(*) >= 2
        ORDER BY random()
    """).fetchall()
    return [(r[0], "phase_voyage", r[0], r[1]) for r in rows]
    # (voyage_key, source_type, source_id, text)


def load_thread_sources(conn: psycopg.Connection) -> list[tuple]:
    rows = conn.execute("""
        SELECT voyage_key, thread_id::text, subject, summary
        FROM thread_summaries
        WHERE summary IS NOT NULL AND summary <> ''
        ORDER BY random()
    """).fetchall()
    return [(r[0], "thread", r[1], r[3]) for r in rows]
    # (voyage_key, source_type, source_id, text)


def main(target: int = 200, workers: int = 4, source: str = "both") -> None:
    conn = psycopg.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("""
        SELECT question_id FROM ground_truth
        WHERE question_type = 'investigative'
        ORDER BY question_id DESC LIMIT 1
    """)
    row = cur.fetchone()
    last_num = int(row[0].split("_")[1]) if row else 0

    sources: list[tuple] = []
    if source in ("phases", "both"):
        sources += load_phase_sources(conn)
    if source in ("threads", "both"):
        sources += load_thread_sources(conn)
    conn.close()

    if not sources:
        print("No sources found.")
        return

    # Shuffle and cap at a reasonable multiple of target
    import random
    random.shuffle(sources)
    sources = sources[:target * 2]

    print(f"Sources: {len(sources)} | workers: {workers} | target: {target} | starting at qi_{last_num + 1:04d}")

    client, model = make_llm_client()

    q_counter = last_num + 1
    done = 0
    inserted = 0

    write_conn = psycopg.connect(DATABASE_URL)
    write_cur = write_conn.cursor()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(generate_question, client, model, src_type, src_id, vk, text): (vk, src_type, src_id)
            for vk, src_type, src_id, text in sources
        }

        for future in as_completed(futures):
            done += 1
            if done % 10 == 0 or done == 1:
                print(f"  {done}/{len(sources)} processed, {inserted} Q&As inserted")

            if inserted >= target:
                continue

            result = future.result()
            if result:
                write_cur.execute("""
                    INSERT INTO ground_truth
                        (question_id, question, ground_truth_answer, difficulty,
                         source_type, source_id, source_chunk_id, voyage_key, question_type)
                    VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, 'investigative')
                    ON CONFLICT (question_id) DO NOTHING
                """, (
                    f"qi_{q_counter:04d}",
                    result["question"],
                    result["answer"],
                    result["difficulty"],
                    result["source_type"],
                    result["source_id"],
                    result["voyage_key"],
                ))
                write_conn.commit()
                q_counter += 1
                inserted += 1

    write_conn.close()
    print(f"\nDone. {inserted} investigative Q&A pairs inserted from {len(sources)} sources.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=200,
                        help="Target number of Q&A pairs (default: 200)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Parallel workers (default: 4)")
    parser.add_argument("--source", choices=["phases", "threads", "both"], default="both",
                        help="Which source to use (default: both)")
    args = parser.parse_args()
    main(target=args.target, workers=args.workers, source=args.source)
