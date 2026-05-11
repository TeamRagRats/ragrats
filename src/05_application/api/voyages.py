from __future__ import annotations

import psycopg
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from deps import get_db, verify_token

router = APIRouter(prefix="/voyages", tags=["voyages"])


class Voyage(BaseModel):
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
        "SELECT vessel_name, commodity, fixture_fromrange, fixture_torange, "
        "fixture_ldportname, lastdischargeportname "
        "FROM fixtures ORDER BY vessel_name"
    ).fetchall()
    return [
        Voyage(
            vessel_name=r[0],
            commodity=r[1],
            from_range=r[2],
            to_range=r[3],
            load_port=r[4],
            discharge_port=r[5],
        )
        for r in rows
    ]
