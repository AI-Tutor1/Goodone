"""Depreciation Agent — straight-line monthly depreciation per asset class.

Per ``docs/context.md`` §9 and ``docs/accounting_rules.md`` §11:
  laptops 3 years (36mo), furniture 5 years (60mo), office equipment 5 years.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from src.core.money import ZERO_AED, aed
from src.ledger.posting import (
    JournalEntryDraft,
    JournalLineDraft,
    PostedJournal,
    post_journal,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


_EXPENSE_BY_CLASS = {
    "LAPTOP": ("6510", "1112"),
    "FURNITURE": ("6520", "1114"),
    "OFFICE_EQUIPMENT": ("6530", "1116"),
}


@dataclass(frozen=True)
class AssetSchedule:
    asset_id: int
    asset_class: str
    monthly_amount: Decimal


def schedules_for_period(session: Session, *, period: str) -> list[AssetSchedule]:
    """Compute monthly depreciation amount for every asset in service."""
    rows = session.execute(
        text(
            """
            SELECT a.asset_id, a.asset_class, a.cost_aed,
                   a.useful_life_months,
                   COALESCE(SUM(e.monthly_amount_aed), 0) AS accum
            FROM   assets.fixed_assets a
            LEFT JOIN assets.fixed_asset_depreciation_entries e
                   ON e.asset_id = a.asset_id
            WHERE  a.status = 'ACTIVE'
            GROUP  BY a.asset_id, a.asset_class, a.cost_aed, a.useful_life_months
            """,
        ),
    ).all()
    out: list[AssetSchedule] = []
    for r in rows:
        cost = aed(r.cost_aed)
        accum = aed(r.accum)
        remaining = cost - accum
        if remaining <= ZERO_AED:
            continue
        monthly = aed(cost / Decimal(r.useful_life_months))
        if monthly > remaining:
            monthly = remaining
        out.append(
            AssetSchedule(
                asset_id=int(r.asset_id),
                asset_class=str(r.asset_class),
                monthly_amount=monthly,
            )
        )
    return out


def post_monthly_depreciation(
    session: Session,
    *,
    period: str,
    posting_date: date,
    coa,
    sub_ledgers,
) -> list[PostedJournal]:
    """Post one JE per asset class for the period."""
    by_class: dict[str, list[AssetSchedule]] = {}
    for s in schedules_for_period(session, period=period):
        by_class.setdefault(s.asset_class, []).append(s)

    posted: list[PostedJournal] = []
    for klass, schedules in by_class.items():
        total = sum((s.monthly_amount for s in schedules), start=ZERO_AED)
        if total == ZERO_AED:
            continue
        expense_acct, accum_acct = _EXPENSE_BY_CLASS[klass]
        lines = [JournalLineDraft(account_code=expense_acct, debit_aed=total)]
        # one credit line per asset so the sub-ledger can attribute correctly.
        for s in schedules:
            lines.append(
                JournalLineDraft(
                    account_code=accum_acct,
                    credit_aed=s.monthly_amount,
                    sub_ledger_keys={"asset_id": s.asset_id},
                ),
            )
        posted.append(
            post_journal(
                session,
                JournalEntryDraft(
                    date=posting_date,
                    narration=f"Monthly depreciation {klass.lower()} {period}",
                    source="system:depreciation_agent",
                    source_kind="system",
                    source_ref=f"DEP-{period}-{klass}",
                    source_version="0.1",
                    posted_by="system",
                    lines=lines,
                ),
                coa=coa,
                sub_ledgers=sub_ledgers,
            ),
        )
    return posted
