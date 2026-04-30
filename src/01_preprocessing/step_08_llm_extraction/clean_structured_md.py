from __future__ import annotations

# Standalone cleaning script for llm_structured.structured_md.
# Removes Key Information lines that carry no real value (empty, N/A, "Not Specified", etc.).
# Only processes mode='full' rows; classify rows have no Key Information section.
#
# Run from src/preprocessing/:
#   python step_08_llm_extraction/clean_structured_md.py [--dry-run] [--voyage KEY] [--sha256 HASH]

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _here = _Path(__file__).resolve().parent.parent
    _repo_root = _here.parents[1]
    sys.path.insert(0, str(_repo_root))
    sys.path.insert(0, str(_here))
    __package__ = "preprocessing"

import argparse
import re

import psycopg

from core.db import connect

# Matches a Key Information list line whose value is null-ish.
# Label may be bold (**Field**) or plain (Field).
# Value may have trailing parentheticals or extra text after the null keyword —
# e.g. "Not specified (damage during loading)", "None provided", "N/A (test cert)".
_NULL_LINE = re.compile(
    r"""^
    \s*-\s+                             # bullet
    (?:\*\*[^*]+\*\*|[^:*\n]+)         # **Bold Field** or plain Field
    :\s*                                # colon + optional whitespace
    (?:                                 # null-ish value, or empty:
        \[?\s*                          # optional leading [ (e.g. [Not specified])
        (?:
            not\s+(?:specified|applicable|identifiable|available|provided|stated|mentioned)
            |n\s*/\s*a                  # N/A, n/a, N / A …
            |none\b
            |unknown\b
            |tbd\b
        )
        .*                              # trailing text: parentheticals, clauses, etc.
        |\[[^\]]*\].*                   # [any bracket placeholder] + optional trailing text
    )?
    $""",
    re.IGNORECASE | re.VERBOSE,
)

# Matches the ## Key Information section up to (but not including) the next ## heading or EOF.
_KI_SECTION = re.compile(
    r"(^## Key Information[ \t]*\n)(.*?)(?=^##|\Z)",
    re.MULTILINE | re.DOTALL,
)


def clean_key_information(text: str) -> str:
    """Return text with null-value lines stripped from ## Key Information only."""
    def _filter_section(m: re.Match) -> str:
        header = m.group(1)
        body = m.group(2)
        kept = [line for line in body.splitlines(keepends=True) if not _NULL_LINE.match(line)]
        return header + "".join(kept)

    return _KI_SECTION.sub(_filter_section, text)


def _removed_lines(original: str, cleaned: str) -> list[str]:
    orig_lines = set(original.splitlines())
    clean_lines = set(cleaned.splitlines())
    return sorted(orig_lines - clean_lines)


def run(dry_run: bool, voyage: str | None, sha256_filter: str | None) -> None:
    with connect() as conn:
        rows = _fetch_rows(conn, voyage, sha256_filter)
        print(f"Fetched {len(rows)} row(s) to inspect.")

        changed = 0
        for sha, text in rows:
            cleaned = clean_key_information(text)
            if cleaned == text:
                continue

            removed = _removed_lines(text, cleaned)
            changed += 1
            if dry_run:
                print(f"\n[DRY RUN] {sha[:12]}… — {len(removed)} line(s) would be removed:")
                for line in removed:
                    print(f"  - {line.strip()}")
            else:
                _update_row(conn, sha, cleaned)

        if dry_run:
            print(f"\nDry run complete: {changed}/{len(rows)} row(s) would be updated.")
        else:
            print(f"Done: {changed}/{len(rows)} row(s) updated.")


def _fetch_rows(
    conn: psycopg.Connection,
    voyage: str | None,
    sha256_filter: str | None,
) -> list[tuple[str, str]]:
    parts = [
        "SELECT s.sha256, s.structured_md "
        "FROM llm_structured s "
    ]
    params: list = []

    if voyage:
        parts.append(
            "JOIN llm_load_queue q ON q.sha256 = s.sha256 "
            "WHERE s.mode = 'full' AND s.structured_md IS NOT NULL "
            "AND q.voyage_key = %s "
        )
        params.append(voyage)
    else:
        parts.append("WHERE s.mode = 'full' AND s.structured_md IS NOT NULL ")

    if sha256_filter:
        parts.append("AND s.sha256 = %s ")
        params.append(sha256_filter)

    with conn.cursor() as cur:
        cur.execute("".join(parts), params)
        return cur.fetchall()


def _update_row(conn: psycopg.Connection, sha256: str, cleaned: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE llm_structured SET structured_md = %s WHERE sha256 = %s",
            (cleaned, sha256),
        )
    conn.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Strip empty/N/A lines from Key Information in llm_structured.structured_md."
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing.")
    parser.add_argument("--voyage", metavar="KEY", help="Limit to a single voyage key.")
    parser.add_argument("--sha256", metavar="HASH", help="Limit to a single document sha256.")
    args = parser.parse_args()

    run(dry_run=args.dry_run, voyage=args.voyage, sha256_filter=args.sha256)
