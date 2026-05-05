"""Period close endpoints — status, pre-close, close, reopen."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from src.agents import period_close as pc_agent
from src.api.dependencies import db_session, require_cfo
from src.core.exceptions import LedgerError
from src.ledger.coa import get_active_coa
from src.ledger.period import PeriodService
from src.ledger.subledger import build_default_registry

router = APIRouter(prefix="/periods", tags=["periods"])


class PreClosePayload(BaseModel):
    posting_date: date
    closing_rate_aed_per_pkr: Decimal


class ReopenPayload(BaseModel):
    reason: str


@router.get("")
def list_periods(session=Depends(require_cfo), db=Depends(db_session)) -> list[dict]:
    rows = db.execute(
        text(
            "SELECT period, status::text, opened_at, closed_at, closed_by, "
            "       reopened_at, reopened_by "
            "FROM master.periods ORDER BY period DESC",
        ),
    ).all()
    return [dict(r._mapping) for r in rows]


@router.post("/{period}/pre-close")
def pre_close(
    period: str,
    payload: PreClosePayload,
    session=Depends(require_cfo),
    db=Depends(db_session),
) -> dict:
    coa = get_active_coa()
    registry = build_default_registry()
    PeriodService(sub_ledgers=registry).begin_closing(db, period, by=session.user_id)
    summary = pc_agent.run_pre_close(
        db,
        period=period,
        posting_date=payload.posting_date,
        closing_rate_aed_per_pkr=payload.closing_rate_aed_per_pkr,
        coa=coa,
        sub_ledgers=registry,
    )
    return {
        "period": summary.period,
        "fx_jes": [j.je_id for j in summary.fx_jes],
        "depreciation_jes": [j.je_id for j in summary.depreciation_jes],
        "prepaid_jes": [j.je_id for j in summary.prepaid_jes],
        "tuitional_ai_je": (summary.tuitional_ai_je.je_id if summary.tuitional_ai_je else None),
        "intangible_amortization_jes": [j.je_id for j in summary.intangible_amortization_jes],
    }


@router.post("/{period}/close")
def close(
    period: str,
    session=Depends(require_cfo),
    db=Depends(db_session),
) -> dict:
    registry = build_default_registry()
    try:
        result = pc_agent.run_close(db, period=period, by=session.user_id, sub_ledgers=registry)
    except LedgerError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": type(exc).__name__, "message": exc.message, "context": exc.context},
        ) from None
    return asdict(result)


@router.post("/{period}/pre-close-preview")
def pre_close_preview(
    period: str,
    payload: PreClosePayload,
    session=Depends(require_cfo),
    db=Depends(db_session),
) -> dict:
    """Dry-run: runs all T+1 agents inside a SAVEPOINT that is always rolled back.

    Returns the list of JEs that *would* be posted without altering the GL.
    """
    coa = get_active_coa()
    registry = build_default_registry()
    from sqlalchemy import text as _text

    db.execute(_text("SAVEPOINT pre_close_preview"))
    try:
        summary = pc_agent.run_pre_close(
            db,
            period=period,
            posting_date=payload.posting_date,
            closing_rate_aed_per_pkr=payload.closing_rate_aed_per_pkr,
            coa=coa,
            sub_ledgers=registry,
        )
        would_post = {
            "fx_jes": len(summary.fx_jes),
            "depreciation_jes": len(summary.depreciation_jes),
            "prepaid_jes": len(summary.prepaid_jes),
            "tuitional_ai_je": summary.tuitional_ai_je is not None,
            "intangible_amortization_jes": len(summary.intangible_amortization_jes),
        }
    finally:
        db.execute(_text("ROLLBACK TO SAVEPOINT pre_close_preview"))

    return {"period": period, "dry_run": True, "would_post": would_post}


@router.post("/{period}/reopen")
def reopen(
    period: str,
    payload: ReopenPayload,
    session=Depends(require_cfo),
    db=Depends(db_session),
) -> dict:
    registry = build_default_registry()
    try:
        PeriodService(sub_ledgers=registry).reopen(
            db,
            period,
            by=session.user_id,
            reason=payload.reason,
        )
    except LedgerError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": type(exc).__name__, "message": exc.message, "context": exc.context},
        ) from None
    return {"period": period, "status": "REOPENED"}
