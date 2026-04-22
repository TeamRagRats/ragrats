from __future__ import annotations

import re

_VERSION_RE = re.compile(r"^v(\d+)$", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^A-Z0-9_]")


def derive_voyage_key(folder_name: str) -> str:
    parts = [p.strip() for p in folder_name.split(" - ")]
    vessel_raw = parts[0] if parts else folder_name
    vessel = _NON_ALNUM.sub("", vessel_raw.upper().replace(" ", "_"))
    if len(parts) >= 2:
        m = _VERSION_RE.match(parts[1].strip())
        if m:
            return f"{vessel}_{int(m.group(1))}"
    return vessel


if __name__ == "__main__":
    cases = {
        "African Juniper - v1 - Usiminas-Toyota": "AFRICAN_JUNIPER_1",
        "Aphrodite M - v4 - Eramet": "APHRODITE_M_4",
        "Aphrodite M - Owners": "APHRODITE_M",
        "Emil Selmer - v3 - HMT#3 (May13-17) - JHA": "EMIL_SELMER_3",
    }
    for name, expected in cases.items():
        got = derive_voyage_key(name)
        flag = "OK" if got == expected else "FAIL"
        print(f"[{flag}] {name!r:60s} -> {got!r:30s} (want {expected!r})")
