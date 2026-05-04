"""FX rate endpoints — list, manual override."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from src.api.dependencies import db_session, require_cfo, require_session
from src.ingestion.fx import manual_override

router = APIRouter(prefix="/fx", tags=["fx"])


class OverridePayload(BaseModel):
    date: date
    base: str
    quote: str
    rate: Decimal


@router.get("/rates")
def list_rates(
    base: str = "AED",
    quote: str = "PKR",
    limit: int = 60,
    session=Depends(require_session),
    db=Depends(db_session),
) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (date)
                   date, base, quote, rate::text, source
            FROM   master.fx_rates
            WHERE  base = :b AND quote = :q
            ORDER  BY date DESC,
                      CASE source WHEN 'manual' THEN 0 ELSE 1 END
            LIMIT  :limit
            """,
        ),
        {"b": base, "q": quote, "limit": limit},
    ).all()
    return [dict(r._mapping) for r in rows]


@router.post("/override")
def override(
    payload: OverridePayload,
    session=Depends(require_cfo),
    db=Depends(db_session),
) -> dict:
    manual_override(
        db,
        day=payload.date,
        base=payload.base,
        quote=payload.quote,
        rate=payload.rate,
        by=session.user_id,
    )
    return {"ok": True}
