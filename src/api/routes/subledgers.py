"""Sub-ledger views for the dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text

from src.api.dependencies import db_session, require_session

router = APIRouter(prefix="/subledgers", tags=["subledgers"])


@router.get("/wallets")
def student_wallets(session=Depends(require_session), db=Depends(db_session)) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT s.student_id, s.display_id, s.name,
                   COALESCE(SUM(e.delta_aed), 0)::text AS balance_aed,
                   MAX(e.effective_date) AS last_activity,
                   CASE WHEN MAX(e.effective_date) < (CURRENT_DATE - INTERVAL '12 months')
                        THEN true ELSE false END AS dormant
            FROM   master.students s
            LEFT JOIN subledger.student_wallet_entries e
                   ON e.student_id = s.student_id
            GROUP  BY s.student_id, s.display_id, s.name
            ORDER  BY s.display_id
            """,
        ),
    ).all()
    return [dict(row._mapping) for row in rows]


@router.get("/tutor-payables")
def tutor_payables(session=Depends(require_session), db=Depends(db_session)) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT t.tutor_id, t.display_id, t.name, t.payment_currency,
                   COALESCE(SUM(e.delta_aed), 0)::text       AS balance_aed,
                   COALESCE(SUM(e.original_amount), 0)::text AS balance_original
            FROM   master.tutors t
            LEFT JOIN subledger.tutor_payable_entries e ON e.tutor_id = t.tutor_id
            GROUP  BY t.tutor_id, t.display_id, t.name, t.payment_currency
            ORDER  BY t.display_id
            """,
        ),
    ).all()
    return [dict(row._mapping) for row in rows]


@router.get("/fixed-assets")
def fixed_assets(session=Depends(require_session), db=Depends(db_session)) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT a.asset_id, a.asset_class, a.description,
                   a.cost_aed::text                    AS cost_aed,
                   COALESCE(SUM(e.monthly_amount_aed), 0)::text AS accumulated_dep,
                   (a.cost_aed - COALESCE(SUM(e.monthly_amount_aed), 0))::text AS nbv,
                   a.useful_life_months, a.purchase_date, a.status
            FROM   assets.fixed_assets a
            LEFT JOIN assets.fixed_asset_depreciation_entries e
                   ON e.asset_id = a.asset_id
            GROUP  BY a.asset_id, a.asset_class, a.description, a.cost_aed,
                      a.useful_life_months, a.purchase_date, a.status
            ORDER  BY a.asset_id
            """,
        ),
    ).all()
    return [dict(row._mapping) for row in rows]


@router.get("/prepaids")
def prepaids(session=Depends(require_session), db=Depends(db_session)) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT p.prepaid_id, p.account_code, p.description,
                   p.total_aed::text AS total_aed,
                   COALESCE(SUM(e.monthly_amount_aed), 0)::text AS amortised,
                   (p.total_aed - COALESCE(SUM(e.monthly_amount_aed), 0))::text AS unamortised,
                   p.total_months, p.start_date
            FROM   assets.prepaids p
            LEFT JOIN assets.prepaid_amortization_entries e
                   ON e.prepaid_id = p.prepaid_id
            GROUP  BY p.prepaid_id, p.account_code, p.description, p.total_aed,
                      p.total_months, p.start_date
            ORDER  BY p.prepaid_id
            """,
        ),
    ).all()
    return [dict(row._mapping) for row in rows]
