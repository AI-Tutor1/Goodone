"""P&L / Balance Sheet / KPI / Profitability endpoints."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query

from src.agents import profitability, reporting
from src.api.dependencies import db_session, require_session

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/pnl/{period}")
def pnl(period: str, session=Depends(require_session), db=Depends(db_session)) -> dict:
    return asdict(reporting.profit_and_loss(db, period=period))


@router.get("/bs")
def bs(
    as_of: str = Query(..., description="YYYY-MM-DD"),
    session=Depends(require_session),
    db=Depends(db_session),
) -> dict:
    return asdict(reporting.balance_sheet(db, as_of=as_of))


@router.get("/kpis/{period}")
def kpis(period: str, session=Depends(require_session), db=Depends(db_session)) -> dict:
    return asdict(reporting.kpis(db, period=period))


@router.get("/profitability")
def profit(
    period: str | None = None,
    session=Depends(require_session),
    db=Depends(db_session),
) -> list[dict]:
    return [asdict(p) for p in profitability.per_enrollment(db, period=period)]
