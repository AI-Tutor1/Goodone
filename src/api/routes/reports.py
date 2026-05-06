"""P&L / Balance Sheet / KPI / Profitability / Trial Balance / Aging / Cash Flow / Budget."""

from __future__ import annotations

import io
from dataclasses import asdict
from typing import Any, cast

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.agents import profitability, reporting
from src.api.dependencies import db_session, require_session

router = APIRouter(prefix="/reports", tags=["reports"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_xlsx(headers: list[str], rows: list[dict[str, Any]], sheet_name: str = "Report") -> bytes:
    import openpyxl  # type: ignore[import-untyped]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(headers)
    for row in rows:
        ws.append([str(row.get(h, "")) for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _to_pdf(html: str) -> bytes:
    from weasyprint import HTML

    return cast(bytes, HTML(string=html).write_pdf())


def _simple_html(title: str, headers: list[str], rows: list[dict[str, Any]]) -> str:
    th = "".join(f"<th>{h}</th>" for h in headers)
    body = ""
    for row in rows:
        td = "".join(f"<td>{row.get(h, '')}</td>" for h in headers)
        body += f"<tr>{td}</tr>"
    style = "table{border-collapse:collapse}th,td{border:1px solid #ccc;padding:4px}"
    return (
        f"<html><head><style>{style}</style></head>"
        f"<body><h2>{title}</h2><table><thead><tr>{th}</tr></thead>"
        f"<tbody>{body}</tbody></table></body></html>"
    )


# ---------------------------------------------------------------------------
# P&L
# ---------------------------------------------------------------------------


@router.get("/pnl/{period}")
def pnl(
    period: str,
    format: str = Query(default="json", pattern="^(json|xlsx|pdf)$"),
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> Any:
    data = asdict(reporting.profit_and_loss(db, period=period))
    if format == "json":
        return data
    rows = [
        {"account": k, "amount_aed": str(v)}
        for k, v in data.items()
        if isinstance(v, (int, float, str))
    ]
    headers = ["account", "amount_aed"]
    title = f"P&L — {period}"
    if format == "xlsx":
        content = _to_xlsx(headers, rows, sheet_name="PnL")
        return StreamingResponse(
            iter([content]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=pnl-{period}.xlsx"},
        )
    content = _to_pdf(_simple_html(title, headers, rows))
    return StreamingResponse(
        iter([content]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=pnl-{period}.pdf"},
    )


# ---------------------------------------------------------------------------
# Balance Sheet
# ---------------------------------------------------------------------------


@router.get("/bs")
def bs(
    as_of: str = Query(..., description="YYYY-MM-DD"),
    format: str = Query(default="json", pattern="^(json|xlsx|pdf)$"),
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> Any:
    data = asdict(reporting.balance_sheet(db, as_of=as_of))
    if format == "json":
        return data
    rows = [
        {"account": k, "amount_aed": str(v)}
        for k, v in data.items()
        if isinstance(v, (int, float, str))
    ]
    headers = ["account", "amount_aed"]
    title = f"Balance Sheet — {as_of}"
    if format == "xlsx":
        content = _to_xlsx(headers, rows, sheet_name="BalanceSheet")
        return StreamingResponse(
            iter([content]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=bs-{as_of}.xlsx"},
        )
    content = _to_pdf(_simple_html(title, headers, rows))
    return StreamingResponse(
        iter([content]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=bs-{as_of}.pdf"},
    )


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------


@router.get("/kpis/{period}")
def kpis(
    period: str, session: Any = Depends(require_session), db: Session = Depends(db_session)
) -> dict[str, Any]:
    return asdict(reporting.kpis(db, period=period))


# ---------------------------------------------------------------------------
# Profitability
# ---------------------------------------------------------------------------


@router.get("/profitability")
def profit(
    period: str | None = None,
    limit: int = Query(default=100, le=500),
    skip: int = Query(default=0, ge=0),
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    all_rows = [asdict(p) for p in profitability.per_enrollment(db, period=period)]
    return {"rows": all_rows[skip : skip + limit], "limit": limit, "skip": skip}


# ---------------------------------------------------------------------------
# Trial Balance
# ---------------------------------------------------------------------------


@router.get("/trial-balance")
def trial_balance(
    period: str | None = Query(default=None, description="YYYY-MM (omit for all-time)"),
    format: str = Query(default="json", pattern="^(json|xlsx|pdf)$"),
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> Any:
    params: dict[str, Any] = {}
    period_filter = ""
    if period:
        period_filter = "WHERE je.period = :period"
        params["period"] = period

    rows = db.execute(
        text(
            f"""
            SELECT jl.account_code,
                   coa.name AS account_name,
                   SUM(jl.debit_aed)::text  AS total_debit,
                   SUM(jl.credit_aed)::text AS total_credit,
                   (SUM(jl.debit_aed) - SUM(jl.credit_aed))::text AS net_aed
            FROM ledger.journal_lines jl
            JOIN ledger.journal_entries je ON je.je_id = jl.je_id
            LEFT JOIN master.chart_of_accounts coa ON coa.code = jl.account_code
            {period_filter}
            GROUP BY jl.account_code, coa.name
            ORDER BY jl.account_code
            """
        ),
        params,
    ).all()

    data = [dict(r._mapping) for r in rows]
    headers = ["account_code", "account_name", "total_debit", "total_credit", "net_aed"]
    title = f"Trial Balance{' — ' + period if period else ''}"

    if format == "json":
        return {"period": period, "lines": data}
    if format == "xlsx":
        content = _to_xlsx(headers, data, sheet_name="TrialBalance")
        fname = f"trial-balance-{period or 'all'}.xlsx"
        return StreamingResponse(
            iter([content]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={fname}"},
        )
    content = _to_pdf(_simple_html(title, headers, data))
    return StreamingResponse(
        iter([content]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=trial-balance-{period or 'all'}.pdf"
        },
    )


# ---------------------------------------------------------------------------
# AP Aging
# ---------------------------------------------------------------------------


@router.get("/ap-aging")
def ap_aging(
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT t.tutor_id, t.name, t.payment_currency,
                   SUM(CASE WHEN (CURRENT_DATE - je.date) <= 30
                            THEN e.delta_aed ELSE 0 END)::text              AS current_30,
                   SUM(CASE WHEN (CURRENT_DATE - je.date) BETWEEN 31 AND 60
                            THEN e.delta_aed ELSE 0 END)::text              AS days_31_60,
                   SUM(CASE WHEN (CURRENT_DATE - je.date) BETWEEN 61 AND 90
                            THEN e.delta_aed ELSE 0 END)::text              AS days_61_90,
                   SUM(CASE WHEN (CURRENT_DATE - je.date) > 90
                            THEN e.delta_aed ELSE 0 END)::text              AS over_90,
                   SUM(e.delta_aed)::text                                   AS total_owing
            FROM subledger.tutor_payable_entries e
            JOIN master.tutors t ON t.tutor_id = e.tutor_id
            JOIN ledger.journal_entries je ON je.je_id = e.je_id
            WHERE e.delta_aed > 0
            GROUP BY t.tutor_id, t.name, t.payment_currency
            HAVING SUM(e.delta_aed) > 0
            ORDER BY SUM(e.delta_aed) DESC
            """
        )
    ).all()
    return [dict(r._mapping) for r in rows]


# ---------------------------------------------------------------------------
# AR / Deferred Revenue Aging
# ---------------------------------------------------------------------------


@router.get("/ar-aging")
def ar_aging(
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> list[dict[str, Any]]:
    """Student wallet balances bucketed by last activity date.

    Positive balance = credit (student owes no more — company owes sessions).
    This is a contract liability (IFRS 15) rollforward proxy.
    """
    rows = db.execute(
        text(
            """
            SELECT s.student_id, s.display_id, s.name,
                   SUM(CASE WHEN (CURRENT_DATE - e.effective_date) <= 30
                            THEN e.delta_aed ELSE 0 END)::text AS current_30,
                   SUM(CASE WHEN (CURRENT_DATE - e.effective_date) BETWEEN 31 AND 90
                            THEN e.delta_aed ELSE 0 END)::text AS days_31_90,
                   SUM(CASE WHEN (CURRENT_DATE - e.effective_date) > 90
                            THEN e.delta_aed ELSE 0 END)::text AS over_90,
                   SUM(e.delta_aed)::text                      AS total_balance_aed
            FROM subledger.student_wallet_entries e
            JOIN master.students s ON s.student_id = e.student_id
            GROUP BY s.student_id, s.display_id, s.name
            HAVING SUM(e.delta_aed) != 0
            ORDER BY SUM(e.delta_aed) DESC
            """
        )
    ).all()
    return [dict(r._mapping) for r in rows]


# ---------------------------------------------------------------------------
# Tutor Productivity
# ---------------------------------------------------------------------------


@router.get("/tutor-productivity")
def tutor_productivity(
    period: str | None = Query(default=None, description="YYYY-MM"),
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {}
    period_filter = ""
    if period:
        period_filter = "AND ms.period = :period"
        params["period"] = period

    rows = db.execute(
        text(
            f"""
            SELECT t.tutor_id, t.display_id, t.name,
                   COUNT(*)                                                     AS total_sessions,
                   SUM(CASE WHEN ms.conducted_minutes < 52 THEN 1 ELSE 0 END)  AS penalty_sessions,
                   ROUND(
                     100.0 * SUM(CASE WHEN ms.conducted_minutes < 52 THEN 1 ELSE 0 END)
                     / NULLIF(COUNT(*), 0), 1
                   )::text                                                       AS penalty_pct,
                   ROUND(AVG(ms.conducted_minutes), 1)::text                   AS avg_conducted_min,
                   SUM(CASE WHEN ms.status = 'student_absent' THEN 1 ELSE 0 END) AS no_show_count
            FROM master.sessions ms
            JOIN master.enrollments e ON e.enrollment_id = ms.enrollment_id
            JOIN master.tutors t ON t.tutor_id = e.tutor_id
            WHERE 1=1 {period_filter}
            GROUP BY t.tutor_id, t.display_id, t.name
            ORDER BY penalty_sessions DESC
            """
        ),
        params,
    ).all()
    return [dict(r._mapping) for r in rows]


# ---------------------------------------------------------------------------
# Cash Flow Statement (indirect method)
# ---------------------------------------------------------------------------


@router.get("/cash-flow/{period}")
def cash_flow(
    period: str,
    session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    params = {"period": period}

    def _net(account_codes: list[str]) -> str:
        codes = ", ".join(f"'{c}'" for c in account_codes)
        row = db.execute(
            text(
                f"""
                SELECT COALESCE(SUM(jl.debit_aed - jl.credit_aed), 0)::text AS net
                FROM ledger.journal_lines jl
                JOIN ledger.journal_entries je ON je.je_id = jl.je_id
                WHERE je.period = :period AND jl.account_code IN ({codes})
                """
            ),
            params,
        ).one()
        return str(row.net)

    net_income = (
        db.execute(
            text(
                """
            SELECT COALESCE(
                SUM(CASE WHEN jl.account_code LIKE '4%'
                         THEN jl.credit_aed - jl.debit_aed ELSE 0 END) -
                SUM(CASE WHEN jl.account_code LIKE '5%' OR jl.account_code LIKE '6%'
                         THEN jl.debit_aed - jl.credit_aed ELSE 0 END),
            0)::text AS net_income
            FROM ledger.journal_lines jl
            JOIN ledger.journal_entries je ON je.je_id = jl.je_id
            WHERE je.period = :period
            """
            ),
            params,
        )
        .one()
        .net_income
    )

    depreciation = _net(["6510", "6520", "6530"])
    amortization = _net(["6540"])
    change_student_wallets = _net(["2050"])
    change_tutor_payables = _net(["2020", "2030"])
    fx_effect = _net(["7020"])
    investing = _net(["1111", "1121"])
    financing = (
        db.execute(
            text(
                """
            SELECT COALESCE(SUM(jl.credit_aed - jl.debit_aed), 0)::text AS net
            FROM ledger.journal_lines jl
            JOIN ledger.journal_entries je ON je.je_id = jl.je_id
            WHERE je.period = :period AND jl.account_code LIKE '3%'
            """
            ),
            params,
        )
        .one()
        .net
    )

    return {
        "period": period,
        "operating": {
            "net_income": net_income,
            "add_depreciation": depreciation,
            "add_amortization": amortization,
            "change_in_student_wallets": change_student_wallets,
            "change_in_tutor_payables": change_tutor_payables,
        },
        "fx_effect_on_cash": fx_effect,
        "investing": {"fixed_asset_additions": investing},
        "financing": {"equity_injections": financing},
    }
