from __future__ import annotations

import re

# Stub cleaner — improve later. Strips the common header/sig/quote noise only.

_QUOTED_LINE = re.compile(r"^\s*>.*$", re.MULTILINE)
_HEADER_BLOCK = re.compile(
    r"^\s*(From|Sent|To|Cc|Subject|Date):[ \t].*$",
    re.MULTILINE | re.IGNORECASE,
)
_SIG_LINE = re.compile(
    r"^\s*(Best Regards|Kind Regards|Regards|Atenciosamente|Mvh|Med venlig hilsen)\s*,?\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_MULTI_BLANK = re.compile(r"\n{3,}")


def clean_body(body_text: str | None) -> str | None:
    if not body_text:
        return body_text
    s = _QUOTED_LINE.sub("", body_text)
    s = _HEADER_BLOCK.sub("", s)
    s = _SIG_LINE.sub("", s)
    s = _MULTI_BLANK.sub("\n\n", s)
    return s.strip() or None


if __name__ == "__main__":
    sample = "Hi there\n\n> previous msg\nFrom: a@b.c\nSent: now\n\nBest Regards,\nEmil\n"
    print(clean_body(sample))
