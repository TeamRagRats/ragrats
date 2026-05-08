from __future__ import annotations

# Drops paragraphs that contain confidentiality / legal / virus-scan /
# environmental disclaimers. We split the body on blank lines and remove any
# paragraph containing a trigger phrase. Paragraph-level (not line-level) so
# multi-line "This e-mail and any attachments are confidential…" blocks go
# away as a unit instead of leaving headless fragments.

import re

_TRIGGERS = re.compile(
    r"\b("
    r"confidential(?:ity)?"
    r"|intended\s+recipient"
    r"|attorney[\- ]client(?:\s+privilege[d]?)?"
    r"|legally\s+privileged"
    r"|think\s+before\s+(?:you\s+)?print"
    r"|consider\s+the\s+environment"
    r"|save\s+(?:a\s+)?tree[s]?"
    r"|scanned\s+for\s+(?:any\s+)?virus(?:es)?"
    r"|virus[\- ]free"
    r"|free\s+of\s+(?:any\s+known\s+)?virus(?:es)?"
    r"|(?:e[\- ]?mail|message)\s+(?:and\s+any\s+attachments\s+)?(?:is|are)\s+confidential"
    r"|disclaimer\s*[:\-]"
    r"|opinions[^.]{0,80}do\s+not\s+necessarily\s+represent"
    r"|GDPR"
    r"|personal\s+data\s+protection"
    r"|please\s+(?:do\s+not\s+)?(?:print|forward|copy)\s+this\s+(?:e[\- ]?mail|message)"
    r"|unauthori[sz]ed\s+(?:use|disclosure|copying|distribution)"
    r")\b",
    re.IGNORECASE,
)

_PARAGRAPH_SPLIT = re.compile(r"\n[ \t]*\n")


def strip_legal_notices(text: str) -> str:
    if not text:
        return text
    paragraphs = _PARAGRAPH_SPLIT.split(text)
    kept = [p for p in paragraphs if not _TRIGGERS.search(p)]
    return "\n\n".join(kept)


if __name__ == "__main__":
    sample = (
        "Vessel ETA confirmed for May 10.\n"
        "\n"
        "DISCLAIMER: This e-mail and any attachments are confidential and may be\n"
        "legally privileged. If you are not the intended recipient, please notify\n"
        "the sender and delete this message.\n"
        "\n"
        "Please consider the environment before printing this email.\n"
        "\n"
        "Best regards,\n"
        "Emil\n"
    )
    print(repr(strip_legal_notices(sample)))
