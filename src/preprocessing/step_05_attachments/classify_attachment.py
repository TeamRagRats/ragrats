from __future__ import annotations

# Determines whether an attachment is eligible for Docling text extraction.
# Excludes image/* and zip MIME types; all others (PDF, Office, etc.) are marked ready.
# Used by extract_attachments.py to set the docling_ready flag on each WrittenAttachment.

_EXCLUDED_PREFIXES = ("image/",)
_EXCLUDED_TYPES = {"application/zip", "application/x-zip-compressed", "application/x-zip"}


def is_docling_ready(mime_type: str | None) -> bool:
    if not mime_type:
        return True
    m = mime_type.lower()
    return not (any(m.startswith(p) for p in _EXCLUDED_PREFIXES) or m in _EXCLUDED_TYPES)


if __name__ == "__main__":
    for m in ["application/pdf", "image/png", "text/plain", None]:
        print(m, is_docling_ready(m))
