"""Revenue Agent — wallet drawdown + revenue recognition per session."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from src.core.money import ZERO_AED, aed
from src.ledger.posting import (
    JournalEntryDraft,
    JournalLineDraft,
    PostedJournal,
    post_journal,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class RevenueContext:
    session_id: str
    enrollment_id: int
    student_id: int
    posting_date: date
    student_charge_aed: Decimal
    is_student_absent: bool


def build_revenue_draft(ctx: RevenueContext) -> JournalEntryDraft | None:
    """Return the revenue JE for one session.

    * Conducted: ``Dr 2050 / Cr 4010`` for the full session charge.
    * Student-absent: ``Dr 2050 / Cr 4020`` (no-show margin).
    * Teacher-absent / cancelled / no_show: no revenue (caller skips).
    """
    if ctx.student_charge_aed <= ZERO_AED:
        return None

    revenue_account = "4020" if ctx.is_student_absent else "4010"
    return JournalEntryDraft(
        date=ctx.posting_date,
        narration=(
            f"Revenue session={ctx.session_id} student={ctx.student_id} "
            f"({'no-show' if ctx.is_student_absent else 'conducted'})"
        ),
        source="system:revenue_agent",
        source_kind="system",
        source_ref=f"SES-{ctx.session_id}-REV",
        source_version="0.1",
        posted_by="system",
        lines=[
            JournalLineDraft(
                account_code="2050",
                debit_aed=aed(ctx.student_charge_aed),
                sub_ledger_keys={"student_id": ctx.student_id},
            ),
            JournalLineDraft(
                account_code=revenue_account,
                credit_aed=aed(ctx.student_charge_aed),
                dimensions={"enrollment_id": ctx.enrollment_id},
            ),
        ],
    )


def post_revenue(
    session: Session,
    ctx: RevenueContext,
    *,
    coa: Any,
    sub_ledgers: Any,
) -> PostedJournal | None:
    draft = build_revenue_draft(ctx)
    if draft is None:
        return None
    return post_journal(session, draft, coa=coa, sub_ledgers=sub_ledgers)


def post_topup(
    session: Session,
    *,
    student_id: int,
    amount_aed: Decimal,
    posting_date: date,
    posted_by: str,
    source_ref: str | None = None,
    coa: Any,
    sub_ledgers: Any,
) -> PostedJournal:
    """Convenience entry point: wallet top-up via cash."""
    return post_journal(
        session,
        JournalEntryDraft(
            date=posting_date,
            narration=f"Wallet top-up student={student_id}",
            source="import:bank_adapter",
            source_kind="import",
            source_ref=source_ref or f"TOPUP-{student_id}-{posting_date}",
            posted_by=posted_by,
            lines=[
                JournalLineDraft(account_code="1010", debit_aed=aed(amount_aed)),
                JournalLineDraft(
                    account_code="2050",
                    credit_aed=aed(amount_aed),
                    sub_ledger_keys={"student_id": student_id},
                    dimensions={"wallet_type": "TOPUP"},
                ),
            ],
        ),
        coa=coa,
        sub_ledgers=sub_ledgers,
    )
