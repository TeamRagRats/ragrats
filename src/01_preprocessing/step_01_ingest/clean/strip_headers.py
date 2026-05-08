from __future__ import annotations

# Defensive header-line removal. cut_quote() already drops everything from the
# first forwarded-header block onward, but a single stray "Subject: ..." or
# "Sent: ..." line sometimes survives above the cut (e.g. when the writer
# pasted a snippet of headers inline). This pass nukes any solo header line
# that survived. It is intentionally conservative: only matches the canonical
# "Header-Name: value" shape, anchored to start-of-line.

import re

_HEADER_LINE = re.compile(
    r"^[ \t]*(?:From|To|Cc|Bcc|Sent|Date|Subject|Reply-To)[ \t]*:[ \t].*$",
    re.MULTILINE | re.IGNORECASE,
)


def strip_headers(text: str) -> str:
    if not text:
        return text
    return _HEADER_LINE.sub("", text)


if __name__ == "__main__":
    sample = (
        "Hi Emil,\n"
        "Subject: leaked subject line\n"
        "Could you confirm the vessel ETA?\n"
    )
    print(repr(strip_headers(sample)))
