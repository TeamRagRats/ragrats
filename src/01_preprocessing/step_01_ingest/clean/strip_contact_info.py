from __future__ import annotations

# Removes runs of 2+ consecutive contact-info lines (signature blocks). A line
# is "contact-like" if it looks like one of:
#   - phone:    +XX ..., Tel: / Mobile / Mob / Direct / Cell / Fax / M: / T:
#   - email:    bare address line, or "Email: x@y"
#   - title:    Master / Chief Officer / Captain / Operator / Manager / Broker / …
#   - vessel:   IMO 1234567, MMSI 123456789, M/V SOMETHING
#   - web:      bare http(s)://… or www.…
# Blank lines between contact-like lines do not break the run (signatures
# often have spacing). A run is removed only if it contains 2+ actual contact
# lines, so a single phone number embedded in prose is left alone.

import re

_CONTACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*(?:Tel|Phone|Mobile|Mob|Direct|Cell|Fax|M|T|P|F)\s*[:.]\s*[+\d]", re.IGNORECASE),
    re.compile(r"^\s*\+\d[\d\s().\-]{6,}\s*$"),
    re.compile(r"^\s*\(\d{2,5}\)\s*\d[\d\s\-]{5,}\s*$"),
    re.compile(r"^\s*(?:E[\- ]?mail|Email)\s*[:.]\s*\S+@\S+", re.IGNORECASE),
    re.compile(r"^\s*[\w.\-+]+@[\w.\-]+\.\w{2,}\s*$"),
    re.compile(
        r"^\s*(?:Master|Chief\s+Officer|Captain|Operator|Operations\s+Manager|"
        r"Senior\s+Manager|Manager|Charterer|Charter\s+Broker|Shipbroker|"
        r"Broker|Agent|Director|Managing\s+Director|CEO|CFO|COO|CTO)\s*$",
        re.IGNORECASE,
    ),
    re.compile(r"\bIMO\s*[:#]?\s*\d{6,7}\b", re.IGNORECASE),
    re.compile(r"\bMMSI\s*[:#]?\s*\d{8,9}\b", re.IGNORECASE),
    re.compile(r"^\s*(?:https?://|www\.)\S+\s*$", re.IGNORECASE),
    re.compile(r"^\s*M\s*/\s*V\s+\S", re.IGNORECASE),
    re.compile(r"^\s*MV\s+\S", re.IGNORECASE),
)


def _is_contact(line: str) -> bool:
    if not line.strip():
        return False
    return any(p.search(line) for p in _CONTACT_PATTERNS)


def strip_contact_info(text: str) -> str:
    if not text:
        return text
    lines = text.split("\n")
    n = len(lines)
    keep = [True] * n
    i = 0
    while i < n:
        if _is_contact(lines[i]):
            j = i
            while j < n and (_is_contact(lines[j]) or not lines[j].strip()):
                j += 1
            contact_count = sum(1 for k in range(i, j) if _is_contact(lines[k]))
            if contact_count >= 2:
                for k in range(i, j):
                    keep[k] = False
            i = j
        else:
            i += 1
    return "\n".join(line for line, k in zip(lines, keep) if k)


if __name__ == "__main__":
    sample = (
        "Vessel arrives Singapore May 10.\n"
        "\n"
        "Best regards,\n"
        "Emil Nielsen\n"
        "Charterer\n"
        "+45 1234 5678\n"
        "emil@example.com\n"
        "M/V NORTHERN STAR\n"
        "IMO 9123456\n"
    )
    print(repr(strip_contact_info(sample)))
