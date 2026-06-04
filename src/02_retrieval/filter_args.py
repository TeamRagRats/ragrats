"""Shared CLI filter parsing for retrieval (--source-type, --strategy, --chunker).

Used by run_retrieve.py, run_generation.py, and the testing harnesses so the
accepted vocabulary and defaults stay aligned with the chunks table schema.
"""
from __future__ import annotations

VALID_SOURCE_TYPES = {"email", "attachment"}
DEFAULT_SOURCE_TYPES = ["email", "attachment"]
VALID_STRATEGIES = {"plain", "late", "context", "summary"}
DEFAULT_STRATEGIES = ["plain"]
# Chunker labels are open-ended (a window size like '1500'/'1000', or 'naive' for
# whole-text chunks), so there is no fixed vocabulary to validate against.
DEFAULT_CHUNKERS = ["1500"]


def resolve_filter(
    raw: list[str] | None,
    valid: set[str] | None,
    default: list[str],
    name: str,
) -> list[str] | None:
    """Returns None for 'all' (no filter), else a deduped list of validated values.

    valid=None skips membership validation (used for open-ended vocabularies like
    the chunker label) — tokens are only lowercased, deduped and checked non-empty.
    """
    if not raw:
        return list(default)
    if "all" in raw:
        return None
    resolved: list[str] = []
    for v in raw:
        key = v.lower()
        if not key:
            raise ValueError(f"Empty {name} value")
        if valid is not None and key not in valid:
            valid_str = ", ".join(sorted(valid | {"all"}))
            raise ValueError(f"Unknown {name}: {v!r}. Valid: {valid_str}")
        if key not in resolved:
            resolved.append(key)
    return resolved


def resolve_source_types(raw: list[str] | None) -> list[str] | None:
    return resolve_filter(raw, VALID_SOURCE_TYPES, DEFAULT_SOURCE_TYPES, "source-type")


def resolve_strategies(raw: list[str] | None) -> list[str] | None:
    return resolve_filter(raw, VALID_STRATEGIES, DEFAULT_STRATEGIES, "strategy")


def resolve_chunkers(raw: list[str] | None) -> list[str] | None:
    """Open-ended chunker filter: any label accepted; 'all' → None (no filter)."""
    return resolve_filter(raw, None, DEFAULT_CHUNKERS, "chunker")
