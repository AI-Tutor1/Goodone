"""FX rate endpoints — list, manual override."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

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
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> list[dict[str, Any]]:
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


@router.get("/rates/history")
def rate_history(
    base: str = "AED",
    quote: str = "PKR",
    from_date: str | None = Query(default=None, alias="from", description="YYYY-MM-DD"),
    to_date: str | None = Query(default=None, alias="to", description="YYYY-MM-DD"),
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> list[dict[str, Any]]:
    filters = "WHERE base = :b AND quote = :q"
    params: dict[str, Any] = {"b": base, "q": quote}
    if from_date:
        filters += " AND date >= :from_date"
        params["from_date"] = from_date
    if to_date:
        filters += " AND date <= :to_date"
        params["to_date"] = to_date
    rows = db.execute(
        text(
            f"""
            SELECT DISTINCT ON (date)
                   date, base, quote, rate::text, source
            FROM   master.fx_rates
            {filters}
            ORDER  BY date ASC,
                      CASE source WHEN 'manual' THEN 0 ELSE 1 END
            """
        ),
        params,
    ).all()
    return [dict(r._mapping) for r in rows]


@router.post("/override")
def override(
    payload: OverridePayload,
    session: Any = Depends(require_cfo),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    manual_override(
        db,
        day=payload.date,
        base=payload.base,
        quote=payload.quote,
        rate=payload.rate,
        by=session.user_id,
    )
    return {"ok": True}
