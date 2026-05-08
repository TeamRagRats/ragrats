from __future__ import annotations

# Read-only sampler used to tune the email cleaning regexes against real data.
# Pulls 100 random body_text rows from the emails table, dumps each to
# tools/_samples/<email_id>.txt, and prints a frequency table of markers we
# expect the cleaning rules to match. One-shot script; can be deleted once the
# regexes are tuned. Requires SSH tunnel to the Spark DB up first:
#   ssh -N -L 5433:localhost:5433 golddigger@spark-14d0
# Then DATABASE_URL in .env must point at localhost:5433.

if __name__ == "__main__" and __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _repo_root = _Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(_repo_root))

import re
from collections import Counter
from pathlib import Path

from core.db import connect

_SAMPLE_DIR = Path(__file__).resolve().parent / "_samples"
_SAMPLE_SIZE = 100

_MARKERS: dict[str, re.Pattern[str]] = {
    "quoted_line (^>)":         re.compile(r"^\s*>", re.MULTILINE),
    "original_message_sep":     re.compile(r"-----\s*Original Message\s*-----", re.IGNORECASE),
    "on_x_wrote":               re.compile(r"\bOn\b.{1,200}\bwrote\s*:", re.IGNORECASE | re.DOTALL),
    "from_header_line":         re.compile(r"^\s*From\s*:", re.MULTILINE | re.IGNORECASE),
    "to_header_line":           re.compile(r"^\s*To\s*:",   re.MULTILINE | re.IGNORECASE),
    "sent_header_line":         re.compile(r"^\s*Sent\s*:", re.MULTILINE | re.IGNORECASE),
    "subject_header_line":      re.compile(r"^\s*Subject\s*:", re.MULTILINE | re.IGNORECASE),
    "long_underscore_sep":      re.compile(r"_{8,}"),
    "long_dash_sep":            re.compile(r"-{8,}"),
    "long_equals_sep":          re.compile(r"={8,}"),
    "imo_number":               re.compile(r"\bIMO[ :#]*\d{6,7}\b", re.IGNORECASE),
    "mmsi_number":              re.compile(r"\bMMSI[ :#]*\d{8,9}\b", re.IGNORECASE),
    "phone_intl":               re.compile(r"(?:\+|00)\d[\d \-().]{6,}"),
    "tel_label":                re.compile(r"\b(?:Tel|Phone|Mobile|Mob|Direct|Cell)\s*[:\.]", re.IGNORECASE),
    "email_only_line":          re.compile(r"^\s*[\w.\-+]+@[\w.\-]+\.\w+\s*$", re.MULTILINE),
    "title_master":             re.compile(r"\b(?:Master|Chief\s+Officer|Captain|Operator|Manager|Charterer|Broker)\b", re.IGNORECASE),
    "confidential":             re.compile(r"\bconfidential\b", re.IGNORECASE),
    "disclaimer":               re.compile(r"\bdisclaimer\b", re.IGNORECASE),
    "virus_scan":               re.compile(r"\bvirus(?:\s+(?:scan|free|check))?\b", re.IGNORECASE),
    "think_before_print":       re.compile(r"think\s+before\s+(?:you\s+)?print", re.IGNORECASE),
    "gdpr_privacy":             re.compile(r"\b(?:GDPR|privacy\s+policy|personal\s+data)\b", re.IGNORECASE),
    "html_tag":                 re.compile(r"<[A-Za-z/!][^>]{0,200}>"),
    "html_entity_named":        re.compile(r"&(?:nbsp|amp|lt|gt|quot|apos|copy|reg|hellip|mdash|ndash);"),
    "html_entity_numeric":      re.compile(r"&#\d{2,5};"),
}


def _load_samples() -> list[tuple[str, str, str, str]]:
    sql = """
    SELECT email_id::text, voyage_key, direction, body_text
    FROM   emails
    WHERE  body_text IS NOT NULL
      AND  length(body_text) > 50
    ORDER BY random()
    LIMIT  %s
    """
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (_SAMPLE_SIZE,))
            return [(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]


def _write_samples(rows: list[tuple[str, str, str, str]]) -> None:
    _SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    for f in _SAMPLE_DIR.glob("*.txt"):
        f.unlink()
    for email_id, voyage_key, direction, body in rows:
        header = f"# email_id: {email_id}\n# voyage_key: {voyage_key}\n# direction: {direction}\n# length: {len(body)}\n{'-' * 60}\n"
        (_SAMPLE_DIR / f"{email_id}.txt").write_text(header + body, encoding="utf-8")


def _frequency_table(rows: list[tuple[str, str, str, str]]) -> tuple[Counter, Counter]:
    rows_with_match: Counter = Counter()
    total_matches: Counter = Counter()
    for _eid, _vk, _dir, body in rows:
        for name, pat in _MARKERS.items():
            n = len(pat.findall(body))
            if n:
                rows_with_match[name] += 1
                total_matches[name] += n
    return rows_with_match, total_matches


def main() -> None:
    rows = _load_samples()
    if not rows:
        print("no rows returned — DB empty or filter too tight")
        return
    _write_samples(rows)
    rows_with_match, total_matches = _frequency_table(rows)

    n = len(rows)
    print(f"sampled {n} bodies (avg length {sum(len(r[3]) for r in rows) // n} chars)")
    print(f"samples written to {_SAMPLE_DIR}")
    print()
    print(f"{'marker':30s}  {'rows':>5s}  {'pct':>5s}  {'total':>6s}")
    print(f"{'-' * 30}  {'-' * 5}  {'-' * 5}  {'-' * 6}")
    for name in _MARKERS:
        rcount = rows_with_match.get(name, 0)
        tcount = total_matches.get(name, 0)
        pct = 100.0 * rcount / n
        print(f"{name:30s}  {rcount:5d}  {pct:4.0f}%  {tcount:6d}")


if __name__ == "__main__":
    main()
