from __future__ import annotations

# Reads the ARC_FIXTURES xlsx into a list of dicts, adding a voyage_key derived
# from vessel_name + voyage_no via derive_fixture_key. Used in run_ingest.py.

from pathlib import Path

import pandas as pd

from step_01_ingest.discover.derive_fixture_key import derive_fixture_key


def _clean(v: object) -> object:
    if v is pd.NaT:
        return None
    if isinstance(v, float) and v != v:  # float NaN
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    return v


def read_fixtures_xlsx(path: Path) -> list[dict]:
    df = pd.read_excel(path, engine="openpyxl")
    df.columns = [c.lower() for c in df.columns]
    rows: list[dict] = []
    for _, row in df.iterrows():
        voyage_key = derive_fixture_key(row["vessel_name"], row["voyage_no"])
        d: dict = {"voyage_key": voyage_key}
        for col, val in row.items():
            d[col] = _clean(val)
        rows.append(d)
    return rows
