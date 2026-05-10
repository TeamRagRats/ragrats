from __future__ import annotations

import json
import sys

from config import CATEGORIES
from prompts import SYSTEM_PROMPT, build_user_message


def _extract_objects(text: str) -> list[dict]:
    """Extract complete JSON objects from a potentially truncated array."""
    objects = []
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(text[start : i + 1])
                    if isinstance(obj, dict):
                        objects.append(obj)
                except json.JSONDecodeError:
                    pass
                start = None
    return objects


def _as_str(val) -> str:
    return val.strip() if isinstance(val, str) else ""


def _validate(items: list[dict]) -> list[dict]:
    valid = []
    for item in items:
        if not isinstance(item, dict):
            continue
        question = _as_str(item.get("question"))
        answer = _as_str(item.get("answer"))
        category = _as_str(item.get("category"))
        source_hint = _as_str(item.get("source_hint")) or None
        if not question or not answer or category not in CATEGORIES:
            continue
        valid.append({
            "question": question,
            "answer": answer,
            "category": category,
            "source_hint": source_hint,
        })
    return valid


_JSON_MODE = {"type": "json_object"}


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
        raw = llm.chat(
            SYSTEM_PROMPT, user_msg,
            temperature=0.3, max_tokens=4096,
            response_format=_JSON_MODE,
        )
    except Exception as exc:
        print(f"  [warn] LLM call failed: {exc}", file=sys.stderr)
        return []

    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 1)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0].strip()

    # Try full parse first
    try:
        data = json.loads(text)
        # Unwrap {"questions": [...]} envelope from json_object mode
        if isinstance(data, dict):
            data = data.get("questions") or data.get("items") or list(data.values())[0] if data else []
        if isinstance(data, list):
            return _validate(data)
    except json.JSONDecodeError:
        pass

    # Fall back to extracting whatever complete objects exist
    objects = _extract_objects(text)
    if objects:
        return _validate(objects)

    print(f"  [warn] no valid objects in response: {text[:200]}", file=sys.stderr)
    return []
