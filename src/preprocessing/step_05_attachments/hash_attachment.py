from __future__ import annotations

import hashlib


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


if __name__ == "__main__":
    print(sha256_hex(b"hello"))
