from __future__ import annotations

# Converts a vessel name and voyage number from the fixtures xlsx into a stable
# uppercase key (e.g. "VESSEL_NAME_3"). Used by read_fixtures_xlsx.py.

import re


def derive_fixture_key(vessel_name: str, voyage_no: int | float) -> str:
    name = re.sub(r"[^A-Z0-9]+", "_", str(vessel_name).upper()).strip("_")
    return f"{name}_{int(voyage_no)}"
