"""Amortization Agent — monthly amortization for prepaids + intangibles +
the Tuitional AI capitalisation reclass."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

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


# ---------------------------------------------------------------------------
# Prepaid amortization
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PrepaidSchedule:
    prepaid_id: int
    account_code: str
    monthly_amount: Decimal


_PREPAID_EXPENSE = {
    "1051": "6310",  # LMS prepaid → LMS amortization expense
    "1052": "6480",  # other prepaid → other G&A
}


def prepaid_schedules(session: Session) -> list[PrepaidSchedule]:
    rows = session.execute(
        text(
            """
            SELECT p.prepaid_id, p.account_code, p.total_aed, p.total_months,
                   COALESCE(SUM(e.monthly_amount_aed), 0) AS amortised
            FROM   assets.prepaids p
            LEFT JOIN assets.prepaid_amortization_entries e
                   ON e.prepaid_id = p.prepaid_id
            GROUP  BY p.prepaid_id, p.account_code, p.total_aed, p.total_months
            """,
        ),
    ).all()
    out: list[PrepaidSchedule] = []
    for r in rows:
        total = aed(r.total_aed)
        amortised = aed(r.amortised)
        remaining = total - amortised
        if remaining <= ZERO_AED:
            continue
        monthly = aed(total / Decimal(r.total_months))
        if monthly > remaining:
            monthly = remaining
        out.append(PrepaidSchedule(int(r.prepaid_id), str(r.account_code), monthly))
    return out


def post_prepaid_amortization(
    session: Session,
    *,
    period: str,
    posting_date: date,
    coa: Any,
    sub_ledgers: Any,
) -> list[PostedJournal]:
    posted: list[PostedJournal] = []
    for s in prepaid_schedules(session):
        expense = _PREPAID_EXPENSE[s.account_code]
        posted.append(
            post_journal(
                session,
                JournalEntryDraft(
                    date=posting_date,
                    narration=(f"Monthly amortization prepaid={s.prepaid_id} {period}"),
                    source="system:amortization_agent",
                    source_kind="system",
                    source_ref=f"AMORT-{period}-PRE-{s.prepaid_id}",
                    source_version="0.1",
                    posted_by="system",
                    lines=[
                        JournalLineDraft(
                            account_code=expense,
                            debit_aed=s.monthly_amount,
                        ),
                        JournalLineDraft(
                            account_code=s.account_code,
                            credit_aed=s.monthly_amount,
                            sub_ledger_keys={"prepaid_id": s.prepaid_id},
                        ),
                    ],
                ),
                coa=coa,
                sub_ledgers=sub_ledgers,
            ),
        )
    return posted


# ---------------------------------------------------------------------------
# Tuitional AI capitalization (pre-launch reclass)
# ---------------------------------------------------------------------------


def post_tuitional_ai_capitalization(
    session: Session,
    *,
    intangible_id: int,
    amount_aed: Decimal,
    period: str,
    posting_date: date,
    coa: Any,
    sub_ledgers: Any,
) -> PostedJournal:
    """Reclassify monthly dev cost from 6120 to 1121 per accounting_rules.md §12b."""
    return post_journal(
        session,
        JournalEntryDraft(
            date=posting_date,
            narration=f"Tuitional AI capitalization {period}",
            source="system:amortization_agent",
            source_kind="system",
            source_ref=f"CAP-AI-{period}",
            source_version="0.1",
            posted_by="system",
            lines=[
                JournalLineDraft(
                    account_code="1121",
                    debit_aed=aed(amount_aed),
                    sub_ledger_keys={"intangible_id": intangible_id},
                ),
                JournalLineDraft(account_code="6120", credit_aed=aed(amount_aed)),
            ],
        ),
        coa=coa,
        sub_ledgers=sub_ledgers,
    )


def post_intangible_amortization(
    session: Session,
    *,
    intangible_id: int,
    monthly_amount_aed: Decimal,
    period: str,
    posting_date: date,
    coa: Any,
    sub_ledgers: Any,
) -> PostedJournal:
    """Post-launch monthly intangible amortization (Dr 6540 / Cr 1123)."""
    return post_journal(
        session,
        JournalEntryDraft(
            date=posting_date,
            narration=f"Intangible amortization {period}",
            source="system:amortization_agent",
            source_kind="system",
            source_ref=f"AMORT-INT-{period}-{intangible_id}",
            source_version="0.1",
            posted_by="system",
            lines=[
                JournalLineDraft(account_code="6540", debit_aed=aed(monthly_amount_aed)),
                JournalLineDraft(
                    account_code="1123",
                    credit_aed=aed(monthly_amount_aed),
                    sub_ledger_keys={"intangible_id": intangible_id},
                ),
            ],
        ),
        coa=coa,
        sub_ledgers=sub_ledgers,
    )
