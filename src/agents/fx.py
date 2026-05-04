"""FX Agent — month-end revaluation + realized gain/loss on payment.

Per ``docs/accounting_rules.md`` §9–§10 and ``docs/ifrs_treatments.md``:

* **Unrealized (month-end revaluation, §10):** for each tutor with an
  open PKR balance, recompute the AED equivalent at the closing rate
  vs. the booked-AED. Post the delta to ``7020 FX Gain/Loss — Unrealized``
  paired with ``2020 Tutor Payable — PKR``. The next period's first day
  carries an automatic reverse, set up via ``reverses_je_id`` on the
  reverse JE the agent emits at T+1 of the next period.

* **Realized (payment day, §9):** when paying a tutor on the 10th, post
  ``Dr 2020 / Cr 1010 + 7010`` for the difference between accrual-rate
  AED and payment-rate AED.
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


# ---------------------------------------------------------------------------
# Unrealized FX revaluation (T+1 of next period)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TutorPkrPosition:
    tutor_id: int
    pkr_balance: Decimal  # the original-currency open balance
    booked_aed: Decimal  # what's currently in the GL


def open_pkr_positions(session: Session) -> list[TutorPkrPosition]:
    """Sum unpaid tutor accruals per tutor in PKR + AED."""
    rows = session.execute(
        text(
            """
            SELECT tutor_id,
                   COALESCE(SUM(original_amount), 0) AS pkr_balance,
                   COALESCE(SUM(delta_aed),       0) AS booked_aed
            FROM   subledger.tutor_payable_entries
            WHERE  original_currency = 'PKR'
            GROUP  BY tutor_id
            HAVING COALESCE(SUM(delta_aed), 0) > 0
            """,
        ),
    ).all()
    return [
        TutorPkrPosition(
            tutor_id=int(r.tutor_id),
            pkr_balance=Decimal(r.pkr_balance),
            booked_aed=aed(r.booked_aed),
        )
        for r in rows
    ]


def revalue_unrealized(
    session: Session,
    *,
    posting_date: date,
    closing_rate_aed_per_pkr: Decimal,  # AED for one PKR
    coa,
    sub_ledgers,
) -> list[PostedJournal]:
    """Post one JE per tutor whose AED-equivalent has shifted from booked.

    Sign convention (per ``accounting_rules.md`` §10):
      revalued_aed > booked_aed (PKR strengthened) → debit 7020 (loss).
      revalued_aed < booked_aed                    → credit 7020 (gain).
    """
    posted: list[PostedJournal] = []
    for pos in open_pkr_positions(session):
        revalued_aed = aed(pos.pkr_balance * Decimal(closing_rate_aed_per_pkr))
        delta = aed(revalued_aed - pos.booked_aed)
        if delta == ZERO_AED:
            continue
        if delta > ZERO_AED:
            # Liability grew → loss.
            lines = [
                JournalLineDraft(account_code="7020", debit_aed=delta),
                JournalLineDraft(
                    account_code="2020",
                    credit_aed=delta,
                    sub_ledger_keys={"tutor_id": pos.tutor_id},
                    original_currency="PKR",
                    original_amount=pos.pkr_balance,
                    fx_rate=Decimal(closing_rate_aed_per_pkr),
                ),
            ]
        else:
            amount = -delta
            lines = [
                JournalLineDraft(
                    account_code="2020",
                    debit_aed=amount,
                    sub_ledger_keys={"tutor_id": pos.tutor_id},
                    original_currency="PKR",
                    original_amount=pos.pkr_balance,
                    fx_rate=Decimal(closing_rate_aed_per_pkr),
                ),
                JournalLineDraft(account_code="7020", credit_aed=amount),
            ]
        posted.append(
            post_journal(
                session,
                JournalEntryDraft(
                    date=posting_date,
                    narration=(
                        f"Month-end FX revaluation tutor={pos.tutor_id} "
                        f"(closing AED/PKR={closing_rate_aed_per_pkr})"
                    ),
                    source="system:fx_agent",
                    source_kind="system",
                    source_ref=f"FX-REVAL-{posting_date}-{pos.tutor_id}",
                    source_version="0.1",
                    posted_by="system",
                    lines=lines,
                ),
                coa=coa,
                sub_ledgers=sub_ledgers,
            ),
        )
    return posted


# ---------------------------------------------------------------------------
# Realized FX (payment day)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PayoutLine:
    tutor_id: int
    accrued_aed: Decimal  # what's in the GL
    paid_aed: Decimal  # what we actually wired (PKR / payment_rate)


def post_payment(
    session: Session,
    *,
    posting_date: date,
    payouts: list[PayoutLine],
    coa,
    sub_ledgers,
) -> PostedJournal:
    """Post one consolidated payout JE: Dr 2020 / Cr 1010 + (Dr/Cr 7010)."""
    accrued_total = sum((aed(p.accrued_aed) for p in payouts), start=ZERO_AED)
    paid_total = sum((aed(p.paid_aed) for p in payouts), start=ZERO_AED)
    fx_diff = aed(accrued_total - paid_total)

    lines = [
        JournalLineDraft(
            account_code="2020",
            debit_aed=aed(p.accrued_aed),
            sub_ledger_keys={"tutor_id": p.tutor_id},
        )
        for p in payouts
    ]
    lines.append(JournalLineDraft(account_code="1010", credit_aed=paid_total))
    if fx_diff > ZERO_AED:
        # we accrued more than we paid → realized gain.
        lines.append(JournalLineDraft(account_code="7010", credit_aed=fx_diff))
    elif fx_diff < ZERO_AED:
        lines.append(JournalLineDraft(account_code="7010", debit_aed=-fx_diff))

    return post_journal(
        session,
        JournalEntryDraft(
            date=posting_date,
            narration=f"Tutor payment run {posting_date} ({len(payouts)} tutors)",
            source="system:fx_agent",
            source_kind="system",
            source_ref=f"PAYOUT-{posting_date}",
            source_version="0.1",
            posted_by="system",
            lines=lines,
        ),
        coa=coa,
        sub_ledgers=sub_ledgers,
    )
