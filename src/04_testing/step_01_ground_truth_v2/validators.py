"""
Post-generation validation of LLM-produced Q&A pairs.

Two layers:
  1. Generic-pattern filter (same as original build_ground_truth.py)
  2. Voyage-anchor check: question must mention vessel name or voyage key
"""
from __future__ import annotations

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
    "currently",
    "owners and charterers",
    "charterers and owners",
    "the owners",
    "the charterers",
]


def _has_generic_pattern(question: str) -> bool:
    q = question.lower()
    return any(pattern in q for pattern in _GENERIC_PATTERNS)


def _has_voyage_anchor(question: str, vessel_name: str, voyage_key: str) -> bool:
    q = question.lower()
    return (
        vessel_name.lower() in q
        or voyage_key.lower() in q
        # also accept partial vessel name (first word, e.g. "African" from "African Juniper")
        or vessel_name.split()[0].lower() in q
    )


def is_valid(question: str, answer: str, vessel_name: str, voyage_key: str) -> bool:
    if not question or not answer:
        return False
    if _has_generic_pattern(question):
        return False
    if not _has_voyage_anchor(question, vessel_name, voyage_key):
        return False
    return True
