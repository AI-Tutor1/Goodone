"""Budget module endpoints.

POST /budget/{period}/{account_code}         — upsert a budget entry
GET  /budget/{period}                        — all entries for a period
GET  /reports/budget-vs-actual/{period}      — compare budget to actual GL balances
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.api.dependencies import db_session, require_cfo, require_session

router = APIRouter(tags=["budget"])


class BudgetPayload(BaseModel):
    amount_aed: Decimal
    notes: str | None = None


@router.post("/budget/{period}/{account_code}")
def upsert_budget(
    period: str,
    account_code: str,
    payload: BudgetPayload,
    session: Any = Depends(require_cfo),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    if payload.amount_aed < Decimal("0"):
        raise HTTPException(status_code=400, detail="amount_aed must be >= 0")

    db.execute(
        text(
            """
            INSERT INTO master.budget_entries (period, account_code, amount_aed, notes, created_by)
            VALUES (:period, :code, :amt, :notes, :by)
            ON CONFLICT (period, account_code)
            DO UPDATE SET amount_aed = EXCLUDED.amount_aed,
                          notes = EXCLUDED.notes
            """
        ),
        {
            "period": period,
            "code": account_code,
            "amt": str(payload.amount_aed),
            "notes": payload.notes,
            "by": session.user_id,
        },
    )
    db.commit()
    return {"period": period, "account_code": account_code, "amount_aed": str(payload.amount_aed)}


@router.get("/budget/{period}")
def list_budget(
    period: str,
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT b.budget_id, b.period, b.account_code,
                   a.name AS account_name,
                   b.amount_aed::text, b.notes, b.created_by, b.created_at
            FROM master.budget_entries b
            LEFT JOIN master.chart_of_accounts a ON a.code = b.account_code
            WHERE b.period = :period
            ORDER BY b.account_code
            """
        ),
        {"period": period},
    ).all()
    return [dict(r._mapping) for r in rows]


@router.get("/reports/budget-vs-actual/{period}")
def budget_vs_actual(
    period: str,
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    rows = db.execute(
        text(
            """
            WITH actuals AS (
                SELECT jl.account_code,
                       SUM(jl.debit_aed - jl.credit_aed) AS net_aed
                FROM ledger.journal_lines jl
                JOIN ledger.journal_entries je ON je.je_id = jl.je_id
                WHERE je.period = :period
                GROUP BY jl.account_code
            ),
            budget AS (
                SELECT account_code, amount_aed AS budget_aed
                FROM master.budget_entries
                WHERE period = :period
            )
            SELECT COALESCE(b.account_code, a.account_code)   AS account_code,
                   coa.name                                    AS account_name,
                   COALESCE(b.budget_aed, 0)::text            AS budget_aed,
                   COALESCE(a.net_aed, 0)::text               AS actual_aed,
                   (COALESCE(a.net_aed, 0) - COALESCE(b.budget_aed, 0))::text AS variance_aed
            FROM budget b
            FULL OUTER JOIN actuals a ON a.account_code = b.account_code
            LEFT JOIN master.chart_of_accounts coa
                   ON coa.code = COALESCE(b.account_code, a.account_code)
            ORDER BY COALESCE(b.account_code, a.account_code)
            """
        ),
        {"period": period},
    ).all()
    return {
        "period": period,
        "lines": [dict(r._mapping) for r in rows],
    }
