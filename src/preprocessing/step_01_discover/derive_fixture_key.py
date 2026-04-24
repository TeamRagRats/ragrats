from __future__ import annotations

import re


def derive_fixture_key(vessel_name: str, voyage_no: int | float) -> str:
    name = re.sub(r"[^A-Z0-9]+", "_", str(vessel_name).upper()).strip("_")
    return f"{name}_{int(voyage_no)}"
