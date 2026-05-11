from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from deps import get_db, verify_token

router = APIRouter(prefix="/voyages", tags=["voyages"])


class Voyage(BaseModel):
    voyage_key: str | None
    vessel_name: str | None
    commodity: str | None
    from_range: str | None
    to_range: str | None
    load_port: str | None
    discharge_port: str | None


@router.get("", response_model=list[Voyage])
def list_voyages(
    conn: psycopg.Connection = Depends(get_db),
    _: str = Depends(verify_token),
):
    rows = conn.execute(
        "SELECT voyage_key, vessel_name, commodity, fixture_fromrange, fixture_torange, "
        "fixture_ldportname, lastdischargeportname "
        "FROM fixtures ORDER BY voyage_key"
    ).fetchall()
    return [
        Voyage(
            voyage_key=r[0],
            vessel_name=r[1],
            commodity=r[2],
            from_range=r[3],
            to_range=r[4],
            load_port=r[5],
            discharge_port=r[6],
        )
        for r in rows
    ]
