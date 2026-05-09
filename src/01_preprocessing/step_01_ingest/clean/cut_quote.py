from __future__ import annotations

# Truncates the email body at the earliest quote / forward marker so only the
# writer's new message survives. Markers detected:
#   - any line starting with `>`                               (Outlook/Gmail/Apple quote)
#   - "-----Original Message-----" / "-----Forwarded message-----"
#   - "On <date>, <person> wrote:"  / "Le ... a écrit :"        (Gmail/Apple/French)
#   - a line of 8+ underscores                                  (Outlook quote separator)
#   - 2+ consecutive header-like lines (From:/To:/Sent:/Date:/Subject:/Cc:/Bcc:)
#     within a 6-line window AND containing at least one strong header
#     (From/Sent/Date) AND preceded by at least one content line  (leaked
#     forwarded headers; the strong-header + preceded-by-content guards prevent
#     false positives on operational emails that use TO:/CC:/FM: as body fields)
# The earliest match wins and everything from that line onward is dropped.

import re

_LINE_MARKERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*>"),
    re.compile(r"^\s*-{3,}\s*(?:Original\s+Message|Forwarded\s+message|Forwarded\s+by)\b", re.IGNORECASE),
    re.compile(r"^\s*_{8,}\s*$"),
    re.compile(r"^\s*On\b.{1,300}\bwrote\s*:", re.IGNORECASE),
    re.compile(r"^\s*Le\b.{1,300}\b(?:a\s+écrit|wrote)\s*:", re.IGNORECASE),
)

_HEADER_LINE = re.compile(
    r"^\s*(?:From|To|Cc|Bcc|Sent|Date|Subject|Reply-To)\s*:\s*\S",
    re.IGNORECASE,
)

_STRONG_HEADER_LINE = re.compile(
    r"^\s*(?:From|Sent|Date)\s*:\s*\S",
    re.IGNORECASE,
)


def _earliest_marker(lines: list[str]) -> int:
    earliest = len(lines)
    for i, line in enumerate(lines):
        for pat in _LINE_MARKERS:
            if pat.match(line):
                if i < earliest:
                    earliest = i
                break
    return earliest


def _earliest_header_block(lines: list[str], window: int = 6, min_count: int = 2) -> int:
    n = len(lines)
    i = 0
    while i < n:
        if _HEADER_LINE.match(lines[i]):
            count = 0
            strong = False
            j = i
            while j < min(i + window, n):
                if _HEADER_LINE.match(lines[j]):
                    count += 1
                    if _STRONG_HEADER_LINE.match(lines[j]):
                        strong = True
                elif lines[j].strip():
                    break
                j += 1
            has_content_before = any(lines[k].strip() for k in range(0, i))
            if count >= min_count and strong and has_content_before:
                return i
            i = j if j > i else i + 1
        else:
            i += 1
    return n


def cut_quote(text: str) -> str:
    if not text:
        return text
    lines = text.split("\n")
    cut = min(_earliest_marker(lines), _earliest_header_block(lines))
    if cut >= len(lines):
        return text
    return "\n".join(lines[:cut]).rstrip()


if __name__ == "__main__":
    sample = (
        "Thanks for the update — vessel is on schedule.\n"
        "\n"
        "On Mon, May 5, 2026 at 10:00 AM, Captain <c@x> wrote:\n"
        "> previous message\n"
        "> more quoted text\n"
    )
    print(repr(cut_quote(sample)))
