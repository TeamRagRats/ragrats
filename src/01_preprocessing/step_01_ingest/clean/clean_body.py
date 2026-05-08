from __future__ import annotations

# Orchestrates the body-cleaning pipeline for emails.body_cleaned. Each rule is
# a separate sibling module. The pipeline order is fixed:
#   1. strip_html         — entities, tags, decorative separator runs
#   2. cut_quote          — truncate at first quote / forward marker
#   3. strip_headers      — defensive removal of stray leaked headers
#   4. strip_legal_notices — confidentiality / virus / "think before you print"
#   5. strip_contact_info — runs of 2+ phone/email/title/IMO/MMSI lines
#   6. whitespace normalize — collapse intra-line spaces, trim per-line
#      trailing whitespace, drop space-before-punctuation, collapse 3+ blank
#      lines, .strip(), empty -> None
# Called from run_ingest.py per email and from run_clean_backfill.py per row.

import re

from .cut_quote import cut_quote
from .strip_contact_info import strip_contact_info
from .strip_headers import strip_headers
from .strip_html import strip_html
from .strip_legal_notices import strip_legal_notices

_MULTI_BLANK = re.compile(r"\n{3,}")
_INLINE_WS = re.compile(r"[ \t]{2,}")
_TRAILING_WS = re.compile(r"[ \t]+(\n|$)")
_SPACE_BEFORE_PUNCT = re.compile(r" +([,.;:!?])")


def clean_body(body_text: str | None) -> str | None:
    if not body_text:
        return body_text
    s = strip_html(body_text)
    s = cut_quote(s)
    s = strip_headers(s)
    s = strip_legal_notices(s)
    s = strip_contact_info(s)
    s = _INLINE_WS.sub(" ", s)
    s = _TRAILING_WS.sub(r"\1", s)
    s = _SPACE_BEFORE_PUNCT.sub(r"\1", s)
    s = _MULTI_BLANK.sub("\n\n", s).strip()
    return s or None


if __name__ == "__main__":
    sample = (
        "<p>Dear Captain,</p>"
        "<p>Vessel ETA Singapore <b>10 May</b>. Please confirm berth.</p>"
        "<br>"
        "&mdash; Emil<br>"
        "Charterer<br>"
        "+45 1234 5678<br>"
        "emil@example.com<br>"
        "IMO 9123456<br>"
        "<br>"
        "----------<br>"
        "On Mon, May 5, 2026 at 10:00 AM, Captain &lt;c@x&gt; wrote:<br>"
        "&gt; previous message<br>"
        "&gt; more quoted text<br>"
        "<br>"
        "DISCLAIMER: This e-mail and any attachments are confidential."
    )
    print(repr(clean_body(sample)))
