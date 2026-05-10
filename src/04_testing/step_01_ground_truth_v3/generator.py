from __future__ import annotations

import json
import re
import sys

from prompts import PROMPTS, build_user_message


_BANNED_TOKENS = re.compile(
    r"\b(emails?|e-?mails?|mails?|messages?|pdfs?|documents?|attachments?|"
    r"files?|chunks?|notices?|exchanges?|correspondence|"
    r"the\s+(vessel|ship|cargo|port|charterer|owner|certificate|exchange|notice))\b",
    re.IGNORECASE,
)

_JSON_MODE = {"type": "json_object"}


def _is_clean(question: str) -> bool:
    return _BANNED_TOKENS.search(question) is None


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 1)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.rsplit("```", 1)[0].strip()
    return text


def _parse_one_object(text: str) -> dict | None:
    text = _strip_fences(text)
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            return obj[0]
    except json.JSONDecodeError:
        pass

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
                        return obj
                except json.JSONDecodeError:
                    pass
                start = None
    return None


def _as_str(val) -> str:
    return val.strip() if isinstance(val, str) else ""


def generate_qa(
    llm,
    category: str,
    voyage_key: str,
    vessel_name: str,
    chunk_text: str,
) -> dict | None:
    """Generate one QA pair for the given category. Returns None on failure."""
    if category not in PROMPTS:
        print(f"  [warn] unknown category: {category}", file=sys.stderr)
        return None

    user_msg = build_user_message(voyage_key, vessel_name, chunk_text)
    try:
        raw = llm.chat(
            PROMPTS[category],
            user_msg,
            temperature=0.3,
            max_tokens=1024,
            response_format=_JSON_MODE,
        )
    except Exception as exc:
        print(f"  [warn] LLM call failed ({category}): {exc}", file=sys.stderr)
        return None

    obj = _parse_one_object(raw)
    if obj is None:
        print(f"  [warn] no valid JSON in {category} response: {raw[:200]}", file=sys.stderr)
        return None

    question = _as_str(obj.get("question"))
    answer = _as_str(obj.get("answer"))
    source_hint = _as_str(obj.get("source_hint")) or None

    if not question or not answer:
        return None

    if not _is_clean(question):
        print(f"  [warn] {category} question rejected (banned token): {question[:120]}", file=sys.stderr)
        return None

    if category == "unanswerable" and answer != "NOT_IN_CONTEXT":
        answer = "NOT_IN_CONTEXT"

    return {
        "question": question,
        "answer": answer,
        "category": category,
        "source_hint": source_hint,
    }
