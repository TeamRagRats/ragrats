from __future__ import annotations

# SHA-256 hash of raw attachment bytes. Used by extract_attachments.py to detect
# duplicate files and avoid overwriting distinct content with the same filename.

import hashlib


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


if __name__ == "__main__":
    print(sha256_hex(b"hello"))
