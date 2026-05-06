"""Period Close Agent — orchestrates the T+1 → T+5 monthly close.

Wires together the agents from Phase 4 + the Phase-2 ``PeriodService``:

T+1 (automated):
  1. FX revaluation (per ``accounting_rules.md`` §10).
  2. Depreciation + amortization runs.
  3. Tuitional AI capitalization reclass (until launch).

T+1 → T+5 (CFO action):
  4. Manual JEs as needed.
  5. CFO reviews drafts.

T+5 (close):
  6. Sub-ledger reconciliation (handled by ``PeriodService.close``).
  7. Snapshot + lock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from src.agents.amortization import (
    post_intangible_amortization,
    post_prepaid_amortization,
    post_tuitional_ai_capitalization,
)
from src.agents.depreciation import post_monthly_depreciation
from src.agents.fx import revalue_unrealized
from src.ledger.period import CloseResult, PeriodService

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.ledger.posting import PostedJournal


@dataclass
class PreCloseSummary:
    period: str
    posting_date: date
    fx_jes: list[PostedJournal] = field(default_factory=list)
    depreciation_jes: list[PostedJournal] = field(default_factory=list)
    prepaid_jes: list[PostedJournal] = field(default_factory=list)
    tuitional_ai_je: PostedJournal | None = None
    intangible_amortization_jes: list[PostedJournal] = field(default_factory=list)


def run_pre_close(
    session: Session,
    *,
    period: str,
    posting_date: date,
    closing_rate_aed_per_pkr: Decimal,
    coa: Any,
    sub_ledgers: Any,
    tuitional_ai_intangible_id: int | None = None,
    tuitional_ai_monthly_aed: Decimal | None = None,
    intangible_amortizations: list[tuple[int, Decimal]] | None = None,
) -> PreCloseSummary:
    """Run the deterministic month-end agents.

    Caller (CLI / FastAPI / scheduler) drives this on T+1; the result is
    a manifest of every posted JE that can be displayed in the dashboard
    "Pre-close" panel.
    """
    summary = PreCloseSummary(period=period, posting_date=posting_date)

    summary.fx_jes = revalue_unrealized(
        session,
        posting_date=posting_date,
        closing_rate_aed_per_pkr=closing_rate_aed_per_pkr,
        coa=coa,
        sub_ledgers=sub_ledgers,
    )
    summary.depreciation_jes = post_monthly_depreciation(
        session,
        period=period,
        posting_date=posting_date,
        coa=coa,
        sub_ledgers=sub_ledgers,
    )
    summary.prepaid_jes = post_prepaid_amortization(
        session,
        period=period,
        posting_date=posting_date,
        coa=coa,
        sub_ledgers=sub_ledgers,
    )
    if tuitional_ai_intangible_id is not None and tuitional_ai_monthly_aed is not None:
        summary.tuitional_ai_je = post_tuitional_ai_capitalization(
            session,
            intangible_id=tuitional_ai_intangible_id,
            amount_aed=tuitional_ai_monthly_aed,
            period=period,
            posting_date=posting_date,
            coa=coa,
            sub_ledgers=sub_ledgers,
        )
    for intangible_id, monthly in intangible_amortizations or []:
        summary.intangible_amortization_jes.append(
            post_intangible_amortization(
                session,
                intangible_id=intangible_id,
                monthly_amount_aed=monthly,
                period=period,
                posting_date=posting_date,
                coa=coa,
                sub_ledgers=sub_ledgers,
            ),
        )
    return summary


def run_close(
    session: Session,
    *,
    period: str,
    by: str,
    sub_ledgers: Any,
) -> CloseResult:
    """The T+5 final lock. Reuses ``PeriodService.close``."""
    return PeriodService(sub_ledgers=sub_ledgers).close(session, period, by=by)
