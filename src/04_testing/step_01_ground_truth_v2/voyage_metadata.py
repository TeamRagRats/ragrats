"""
Loads per-voyage metadata needed to anchor ground-truth questions.

Provides:
  - list_voyage_keys()      : all distinct voyage_keys that have chunks
  - vessel_name_from_key()  : "AFRICAN_JUNIPER_1" -> "African Juniper"
  - load_voyage_meta()      : returns VoyageMeta dataclass for one voyage_key
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import psycopg

_TRAILING_NUM = re.compile(r"^(.+)_(\d+)$")


def vessel_name_from_key(voyage_key: str) -> str:
    """Invert derive_voyage_key: AFRICAN_JUNIPER_1 -> 'African Juniper'."""
    m = _TRAILING_NUM.match(voyage_key)
    if m:
        base = m.group(1)
    else:
        base = voyage_key
    return base.replace("_", " ").title()


@dataclass
class VoyageMeta:
    voyage_key: str
    vessel_name: str
    voyage_summary: str
    fixture_summary: str


def list_voyage_keys(conn: psycopg.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT voyage_key FROM chunks ORDER BY voyage_key"
    ).fetchall()
    return [r[0] for r in rows]


def load_voyage_meta(conn: psycopg.Connection, voyage_key: str) -> VoyageMeta:
    vessel_name = vessel_name_from_key(voyage_key)

    row = conn.execute(
        "SELECT summary FROM voyage_summaries WHERE voyage_key = %s",
        (voyage_key,),
    ).fetchone()
    voyage_summary = (row[0] or "").strip() if row else ""

    row = conn.execute(
        "SELECT summary FROM fixture_summaries WHERE voyage_key = %s",
        (voyage_key,),
    ).fetchone()
    fixture_summary = (row[0] or "").strip() if row else ""

    return VoyageMeta(
        voyage_key=voyage_key,
        vessel_name=vessel_name,
        voyage_summary=voyage_summary,
        fixture_summary=fixture_summary,
    )


def load_all_voyage_meta(conn: psycopg.Connection) -> list[VoyageMeta]:
    keys = list_voyage_keys(conn)
    return [load_voyage_meta(conn, k) for k in keys]
