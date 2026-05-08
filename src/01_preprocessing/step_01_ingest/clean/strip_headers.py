from __future__ import annotations

# Defensive header-line removal. cut_quote() already drops everything from the
# first forwarded-header block onward, but a single stray "Subject: ..." or
# "Sent: ..." line sometimes survives above the cut (e.g. when the writer
# pasted a snippet of headers inline). This pass nukes any solo header line
# that survived. It is intentionally conservative: only matches the canonical
# "Header-Name: value" shape, anchored to start-of-line.

import re

# Header labels in languages we see in agent mails. Keep this list flat and
# explicit so it's easy to audit when a new locale slips through.
_HEADER_LABELS = (
    # English
    "From", "To", "Cc", "Bcc", "Sent", "Date", "Subject", "Reply-To",
    # Spanish
    "De", "Para", "Enviado", "Fecha", "Asunto",
    # German
    "Von", "An", "Gesendet", "Datum", "Betreff",
    # French
    "Exp[eé]diteur", "Destinataire", "Envoy[eé]", "Objet",
    # Danish / Norwegian
    "Fra", "Til", "Sendt", "Dato", "Emne",
    # Dutch
    "Aan", "Verzonden", "Onderwerp",
    # Italian
    "Da", "Inviato", "Oggetto",
)

_HEADER_LINE = re.compile(
    r"^[ \t]*(?:" + "|".join(_HEADER_LABELS) + r")[ \t]*:[ \t].*$",
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
