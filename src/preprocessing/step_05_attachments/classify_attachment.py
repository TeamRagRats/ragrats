from __future__ import annotations

# Determines whether an attachment is eligible for Docling text extraction.
# Excludes image/* and archive MIME types (zip, rar, 7z, tar, gz, bz2); all others
# (PDF, Office, etc.) are marked ready. Archives are excluded because Docling cannot
# extract text from them and they would otherwise sit in the queue forever.
# Used by extract_attachments.py to set the docling_ready flag on each WrittenAttachment.

_EXCLUDED_PREFIXES = ("image/",)
_EXCLUDED_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/x-zip",
    "application/x-rar-compressed",
    "application/vnd.rar",
    "application/x-rar",
    "application/x-7z-compressed",
    "application/x-tar",
    "application/gzip",
    "application/x-gzip",
    "application/x-bzip2",
}


def is_docling_ready(mime_type: str | None) -> bool:
    if not mime_type:
        return True
    m = mime_type.lower()
    return not (any(m.startswith(p) for p in _EXCLUDED_PREFIXES) or m in _EXCLUDED_TYPES)


if __name__ == "__main__":
    for m in ["application/pdf", "image/png", "text/plain", None]:
        print(m, is_docling_ready(m))
