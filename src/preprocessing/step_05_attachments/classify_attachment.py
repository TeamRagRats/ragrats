from __future__ import annotations


def is_docling_ready(mime_type: str | None) -> bool:
    if not mime_type:
        return True
    return not mime_type.lower().startswith("image/")


if __name__ == "__main__":
    for m in ["application/pdf", "image/png", "text/plain", None]:
        print(m, is_docling_ready(m))
