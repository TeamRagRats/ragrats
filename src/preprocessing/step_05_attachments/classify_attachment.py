from __future__ import annotations

# Determines whether an attachment is eligible for Docling text extraction.
# Excludes image/* and archive MIME types (zip, rar, 7z, tar, gz, bz2); all others
# (PDF, Office, etc.) are marked ready. Archives are excluded because Docling cannot
# extract text from them and they would otherwise sit in the queue forever.
# Filename extension is also checked because many archives arrive with a generic
# application/octet-stream MIME and would otherwise slip through.
# Used by extract_attachments.py to set the docling_ready flag on each WrittenAttachment.

import os

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
_EXCLUDED_EXTENSIONS = {
    ".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".tbz2", ".xz", ".lz", ".lzma",
}


def is_docling_ready(mime_type: str | None, file_name: str | None = None) -> bool:
    if file_name:
        ext = os.path.splitext(file_name)[1].lower()
        if ext in _EXCLUDED_EXTENSIONS:
            return False
    if not mime_type:
        return True
    m = mime_type.lower()
    return not (any(m.startswith(p) for p in _EXCLUDED_PREFIXES) or m in _EXCLUDED_TYPES)


if __name__ == "__main__":
    cases = [
        ("application/pdf", "report.pdf"),
        ("image/png", "logo.png"),
        ("text/plain", "notes.txt"),
        ("application/octet-stream", "SID.rar"),
        ("application/octet-stream", "data.bin"),
        (None, "archive.7z"),
        (None, None),
    ]
    for mime, name in cases:
        print(mime, name, is_docling_ready(mime, name))
