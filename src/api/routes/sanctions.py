"""Sanctions endpoints — submit, FA decide, CFO decide, list, spend."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.agents import sanctions as sanctions_agent
from src.api.dependencies import db_session, require_cfo, require_fa, require_session
from src.ledger.coa import get_active_coa
from src.ledger.subledger import build_default_registry

router = APIRouter(prefix="/sanctions", tags=["sanctions"])


class SubmitPayload(BaseModel):
    department: str
    title: str
    amount_aed: Decimal


class DecidePayload(BaseModel):
    approve: bool


class SpendPayload(BaseModel):
    expense_account: str
    amount_aed: Decimal
    posting_date: date


@router.post("")
def submit(
    payload: SubmitPayload,
    session: Any = Depends(require_session),  # any authenticated user can submit
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    sid = sanctions_agent.submit(
        db,
        department=payload.department,
        title=payload.title,
        amount_aed=payload.amount_aed,
        created_by=session.user_id,
    )
    return {"id": sid, "status": "PENDING_FA"}


@router.get("")
def list_requests(
    status: str | None = None,
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> list[dict[str, Any]]:
    sql = (
        "SELECT id, department, title, amount_aed::text, status, "
        "       created_at, created_by FROM sanctions.sanction_requests"
    )
    params: dict[str, object] = {}
    if status:
        sql += " WHERE status = :s"
        params["s"] = status
    sql += " ORDER BY id DESC"
    rows = db.execute(text(sql), params).all()
    return [dict(r._mapping) for r in rows]


@router.post("/{request_id}/fa-decide")
def fa_decide(
    request_id: int,
    payload: DecidePayload,
    session: Any = Depends(require_fa),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    sanctions_agent.fa_decide(
        db, request_id=request_id, approve=payload.approve, by=session.user_id
    )
    return {"ok": True}


@router.post("/{request_id}/cfo-decide")
def cfo_decide(
    request_id: int,
    payload: DecidePayload,
    posting_date: date | None = None,
    session: Any = Depends(require_cfo),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    coa = get_active_coa()
    registry = build_default_registry()
    posted = sanctions_agent.cfo_decide(
        db,
        request_id=request_id,
        approve=payload.approve,
        by=session.user_id,
        posting_date=posting_date or date.today(),
        coa=coa,
        sub_ledgers=registry,
    )
    return {
        "ok": True,
        "memo_je_id": posted.je_id if posted else None,
    }


@router.post("/{request_id}/spend")
def spend(
    request_id: int,
    payload: SpendPayload,
    session: Any = Depends(require_cfo),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    coa = get_active_coa()
    registry = build_default_registry()
    try:
        reversal, expense = sanctions_agent.post_spend(
            db,
            request_id=request_id,
            expense_account=payload.expense_account,
            amount_aed=payload.amount_aed,
            posting_date=payload.posting_date,
            by=session.user_id,
            coa=coa,
            sub_ledgers=registry,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {
        "reversal_je_id": reversal.je_id,
        "expense_je_id": expense.je_id,
    }
