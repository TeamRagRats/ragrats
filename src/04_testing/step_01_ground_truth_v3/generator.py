from __future__ import annotations

import json
import sys

from config import CATEGORIES
from prompts import SYSTEM_PROMPT, build_user_message


def generate_qa_batch(
    llm,
    source_type: str,
    voyage_key: str,
    vessel_name: str,
    chunk_text: str,
    n: int,
) -> list[dict]:
    user_msg = build_user_message(source_type, voyage_key, vessel_name, chunk_text, n)
    try:
        raw = llm.chat(SYSTEM_PROMPT, user_msg, temperature=0.3, max_tokens=2000)
    except Exception as exc:
        print(f"  [warn] LLM call failed: {exc}", file=sys.stderr)
        return []

    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 1)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        print(f"  [warn] JSON parse failed: {text[:200]}", file=sys.stderr)
        return []

    if not isinstance(data, list):
        return []

    valid = []
    for item in data:
        if not isinstance(item, dict):
            continue
        question = (item.get("question") or "").strip()
        answer = (item.get("answer") or "").strip()
        category = (item.get("category") or "").strip()
        source_hint = (item.get("source_hint") or "").strip() or None

        if not question or not answer or category not in CATEGORIES:
            continue

        valid.append({
            "question": question,
            "answer": answer,
            "category": category,
            "source_hint": source_hint,
        })

    return valid
