"""Shared CLI filter parsing for retrieval (--source-type, --strategy).

Used by run_retrieve.py, run_generation.py, and the testing harnesses so the
accepted vocabulary and defaults stay aligned with the chunks table schema.
"""
from __future__ import annotations

VALID_SOURCE_TYPES = {"email", "attachment"}
DEFAULT_SOURCE_TYPES = ["email", "attachment"]
VALID_STRATEGIES = {"plain", "late", "context", "summary"}
DEFAULT_STRATEGIES = ["plain"]


def resolve_filter(
    raw: list[str] | None,
    valid: set[str],
    default: list[str],
    name: str,
) -> list[str] | None:
    """Returns None for 'all' (no filter), else a deduped list of validated values."""
    if not raw:
        return list(default)
    if "all" in raw:
        return None
    resolved: list[str] = []
    for v in raw:
        key = v.lower()
        if key not in valid:
            valid_str = ", ".join(sorted(valid | {"all"}))
            raise ValueError(f"Unknown {name}: {v!r}. Valid: {valid_str}")
        if key not in resolved:
            resolved.append(key)
    return resolved


def resolve_source_types(raw: list[str] | None) -> list[str] | None:
    return resolve_filter(raw, VALID_SOURCE_TYPES, DEFAULT_SOURCE_TYPES, "source-type")


def resolve_strategies(raw: list[str] | None) -> list[str] | None:
    return resolve_filter(raw, VALID_STRATEGIES, DEFAULT_STRATEGIES, "strategy")
