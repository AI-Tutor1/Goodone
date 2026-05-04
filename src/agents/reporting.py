"""Reporting Agent — P&L, Balance Sheet, Cash Flow, KPIs.

Reads the GL directly via SQL. Excludes the 9xxx memo range from BS/IS
roll-ups (see ``docs/accounting_rules.md`` §13).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from src.core.money import ZERO_AED, aed

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class ReportLine:
    code: str
    name: str
    amount_aed: Decimal


@dataclass
class ProfitLoss:
    period: str
    revenue: list[ReportLine] = field(default_factory=list)
    cost_of_service: list[ReportLine] = field(default_factory=list)
    operating_expenses: list[ReportLine] = field(default_factory=list)
    non_operating: list[ReportLine] = field(default_factory=list)
    revenue_total: Decimal = ZERO_AED
    cost_total: Decimal = ZERO_AED
    gross_profit: Decimal = ZERO_AED
    opex_total: Decimal = ZERO_AED
    operating_profit: Decimal = ZERO_AED
    non_op_total: Decimal = ZERO_AED
    net_profit: Decimal = ZERO_AED


@dataclass
class BalanceSheet:
    as_of: str
    assets: list[ReportLine] = field(default_factory=list)
    liabilities: list[ReportLine] = field(default_factory=list)
    equity: list[ReportLine] = field(default_factory=list)
    assets_total: Decimal = ZERO_AED
    liabilities_total: Decimal = ZERO_AED
    equity_total: Decimal = ZERO_AED


# ---------------------------------------------------------------------------
# P&L
# ---------------------------------------------------------------------------


def profit_and_loss(session: Session, *, period: str) -> ProfitLoss:
    rows = session.execute(
        text(
            """
            SELECT jl.account_code,
                   coa.name,
                   coa.type::text,
                   COALESCE(SUM(jl.credit_aed - jl.debit_aed), 0) AS credit_normal,
                   COALESCE(SUM(jl.debit_aed - jl.credit_aed), 0) AS debit_normal
            FROM   ledger.journal_lines jl
            JOIN   ledger.journal_entries je ON je.je_id = jl.je_id
            JOIN   master.chart_of_accounts coa ON coa.code = jl.account_code
            WHERE  je.period = :p
              AND  je.status = 'POSTED'
              AND  coa.statement = 'IS'
              AND  coa.is_memo = false
            GROUP  BY jl.account_code, coa.name, coa.type
            ORDER  BY jl.account_code
            """,
        ),
        {"p": period},
    ).all()

    pl = ProfitLoss(period=period)
    for r in rows:
        if r.type == "revenue":
            v = aed(r.credit_normal)
            pl.revenue.append(ReportLine(r.account_code, r.name, v))
            pl.revenue_total += v
        elif r.account_code.startswith("5"):
            v = aed(r.debit_normal)
            pl.cost_of_service.append(ReportLine(r.account_code, r.name, v))
            pl.cost_total += v
        elif r.account_code.startswith("6"):
            v = aed(r.debit_normal)
            pl.operating_expenses.append(ReportLine(r.account_code, r.name, v))
            pl.opex_total += v
        elif r.account_code.startswith("7"):
            # 7xxx mixes revenue (interest) and expense; sign by type.
            v = aed(r.credit_normal) if r.type == "revenue" else aed(r.debit_normal)
            pl.non_operating.append(ReportLine(r.account_code, r.name, v))
            pl.non_op_total += v
    pl.gross_profit = aed(pl.revenue_total - pl.cost_total)
    pl.operating_profit = aed(pl.gross_profit - pl.opex_total)
    pl.net_profit = aed(pl.operating_profit - pl.non_op_total)
    return pl


# ---------------------------------------------------------------------------
# Balance sheet
# ---------------------------------------------------------------------------


def balance_sheet(session: Session, *, as_of: str) -> BalanceSheet:
    rows = session.execute(
        text(
            """
            SELECT jl.account_code, coa.name, coa.type::text,
                   COALESCE(SUM(jl.debit_aed - jl.credit_aed), 0) AS debit_normal,
                   COALESCE(SUM(jl.credit_aed - jl.debit_aed), 0) AS credit_normal
            FROM   ledger.journal_lines jl
            JOIN   ledger.journal_entries je ON je.je_id = jl.je_id
            JOIN   master.chart_of_accounts coa ON coa.code = jl.account_code
            WHERE  je.date <= :as_of
              AND  je.status = 'POSTED'
              AND  coa.statement = 'BS'
              AND  coa.is_memo = false
            GROUP  BY jl.account_code, coa.name, coa.type
            ORDER  BY jl.account_code
            """,
        ),
        {"as_of": as_of},
    ).all()

    bs = BalanceSheet(as_of=as_of)
    for r in rows:
        if r.type == "asset":
            v = aed(r.debit_normal)
            bs.assets.append(ReportLine(r.account_code, r.name, v))
            bs.assets_total += v
        elif r.type == "contra" and r.account_code.startswith("1"):
            v = aed(r.credit_normal)  # accumulated dep / amort = contra-asset
            bs.assets.append(ReportLine(r.account_code, r.name, -v))
            bs.assets_total -= v
        elif r.type == "liability":
            v = aed(r.credit_normal)
            bs.liabilities.append(ReportLine(r.account_code, r.name, v))
            bs.liabilities_total += v
        elif r.type == "equity":
            v = aed(r.credit_normal)
            bs.equity.append(ReportLine(r.account_code, r.name, v))
            bs.equity_total += v
    return bs


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------


@dataclass
class Kpis:
    period: str
    revenue: Decimal
    cost_of_service: Decimal
    gross_profit: Decimal
    gross_margin_pct: Decimal
    operating_profit: Decimal
    net_profit: Decimal
    ebitda: Decimal
    no_show_revenue_share_pct: Decimal


def kpis(session: Session, *, period: str) -> Kpis:
    pl = profit_and_loss(session, period=period)
    revenue = pl.revenue_total
    cost = pl.cost_total
    gross = pl.gross_profit
    margin_pct = (
        (gross / revenue * Decimal("100")).quantize(Decimal("0.01"))
        if revenue > ZERO_AED
        else Decimal("0.00")
    )
    no_show = sum(
        (line.amount_aed for line in pl.revenue if line.code == "4020"),
        start=ZERO_AED,
    )
    no_show_pct = (
        (no_show / revenue * Decimal("100")).quantize(Decimal("0.01"))
        if revenue > ZERO_AED
        else Decimal("0.00")
    )
    da = sum(
        (
            line.amount_aed
            for line in pl.operating_expenses
            if line.code in {"6510", "6520", "6530", "6540"}
        ),
        start=ZERO_AED,
    )
    return Kpis(
        period=period,
        revenue=revenue,
        cost_of_service=cost,
        gross_profit=gross,
        gross_margin_pct=margin_pct,
        operating_profit=pl.operating_profit,
        net_profit=pl.net_profit,
        ebitda=aed(pl.operating_profit + da),
        no_show_revenue_share_pct=no_show_pct,
    )
