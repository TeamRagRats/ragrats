from __future__ import annotations

import re

# Postgres' plainto_tsquery already handles tokenization, lowercasing, and
# stripping non-word characters under the 'simple' config. This wrapper is
# just a defensive normalizer for the raw user input: collapses whitespace
# and replaces punctuation that occasionally trips up the parser when
# embedded in proper nouns (commas in lists, slashes in dates, etc.).
_PUNCT_RE = re.compile(r"[^\w\s]+", flags=re.UNICODE)
_WS_RE = re.compile(r"\s+", flags=re.UNICODE)


def tokenize_query(query: str) -> str:
    """Normalize a raw user query for use with plainto_tsquery('simple', ...).

    Returns a single whitespace-separated string. Empty input returns "".
    """
    if not query:
        return ""
    text = _PUNCT_RE.sub(" ", query)
    text = _WS_RE.sub(" ", text).strip()
    return text.lower()
