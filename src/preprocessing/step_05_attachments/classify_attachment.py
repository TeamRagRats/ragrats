from __future__ import annotations

# Determines whether an attachment is eligible for Docling text extraction.
# Currently excludes image/* MIME types; all others (PDF, Office, etc.) are marked ready.
# Used by extract_attachments.py to set the docling_ready flag on each WrittenAttachment.


def is_docling_ready(mime_type: str | None) -> bool:
    if not mime_type:
        return True
    return not mime_type.lower().startswith("image/")


if __name__ == "__main__":
    for m in ["application/pdf", "image/png", "text/plain", None]:
        print(m, is_docling_ready(m))
