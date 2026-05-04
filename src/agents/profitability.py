"""Profitability Agent — per-enrollment contribution margin and fully-loaded.

Phase-4 ships contribution margin (revenue − direct tutor cost − payment
fees). Fully-loaded (with allocated overhead + amortised CAC) needs Phase-5
allocation rules; a stub method is exposed but returns the contribution
figure with a 0 overhead until Phase 5 wires it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from src.core.money import ZERO_AED, aed

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class EnrollmentProfit:
    enrollment_id: int
    revenue_aed: Decimal
    direct_cost_aed: Decimal
    contribution_margin_aed: Decimal
    contribution_margin_pct: Decimal


def per_enrollment(session: Session, *, period: str | None = None) -> list[EnrollmentProfit]:
    """One row per enrollment that had any activity in *period* (or ever)."""
    where = "WHERE je.status = 'POSTED'"
    params: dict[str, object] = {}
    if period:
        where += " AND je.period = :p"
        params["p"] = period
    # `where` is a hard-coded string literal (no user input); S608 doesn't apply.
    sql = f"""
        SELECT (jl.dimensions->>'enrollment_id')::bigint AS enrollment_id,
               COALESCE(SUM(
                   CASE WHEN jl.account_code IN ('4010', '4020')
                        THEN jl.credit_aed - jl.debit_aed
                        ELSE 0
                   END
               ), 0) AS revenue,
               COALESCE(SUM(
                   CASE WHEN jl.account_code IN ('5010', '5020', '5030', '5040')
                        THEN jl.debit_aed - jl.credit_aed
                        ELSE 0
                   END
               ), 0) AS direct_cost
        FROM   ledger.journal_lines jl
        JOIN   ledger.journal_entries je ON je.je_id = jl.je_id
        {where}
          AND  jl.dimensions ? 'enrollment_id'
        GROUP  BY (jl.dimensions->>'enrollment_id')
        HAVING COALESCE(SUM(jl.debit_aed) + SUM(jl.credit_aed), 0) > 0
        ORDER  BY enrollment_id
        """  # noqa: S608
    rows = session.execute(text(sql), params).all()

    out: list[EnrollmentProfit] = []
    for r in rows:
        revenue = aed(r.revenue)
        cost = aed(r.direct_cost)
        margin = aed(revenue - cost)
        pct = (
            (margin / revenue * Decimal("100")).quantize(Decimal("0.01"))
            if revenue > ZERO_AED
            else Decimal("0.00")
        )
        out.append(
            EnrollmentProfit(
                enrollment_id=int(r.enrollment_id),
                revenue_aed=revenue,
                direct_cost_aed=cost,
                contribution_margin_aed=margin,
                contribution_margin_pct=pct,
            ),
        )
    return out
