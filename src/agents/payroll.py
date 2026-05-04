"""Payroll Agent — penalty math + tutor-fee accrual.

Per ``docs/context.md`` §5 and ``docs/accounting_rules.md`` §3–§5:

* ``conducted >= 52``: full pay, no penalty.
* ``conducted < 52``: prorate by (conducted/scheduled), then × 0.95.
* ``conducted > scheduled``: cap at scheduled.
* ``conducted == 0`` or status ``student_absent``: no tutor cost (no-show margin).

The agent emits a :class:`PayrollDraft` (revenue side handled by
:mod:`src.agents.revenue`); :func:`post_accrual` builds the JE and hands
it to the posting service.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.core.money import ZERO_AED, aed
from src.ledger.posting import (
    JournalEntryDraft,
    JournalLineDraft,
    PostedJournal,
    post_journal,
)

PENALTY_THRESHOLD_MIN = 52
PENALTY_FACTOR = Decimal("0.95")


@dataclass(frozen=True)
class PayrollComputation:
    prorated_aed: Decimal
    net_pay_aed: Decimal
    penalty_aed: Decimal


def compute_payment(
    *,
    tutor_rate_aed: Decimal,
    scheduled_minutes: int,
    conducted_minutes: int,
) -> PayrollComputation:
    """Return the payroll computation for one session.

    Worked example from context.md §5:
      tutor_rate=2500, scheduled=60, conducted=46
      → prorated = 2500 * 46/60 = 1916.67
      → net_pay  = prorated * 0.95 = 1820.83
      → penalty  = prorated - net_pay = 95.84  (note: not 95.83;
                   the engine balances to the cent — see the smoketest
                   golden file's `_note` for the rounding rationale.)
    """
    if conducted_minutes <= 0:
        return PayrollComputation(ZERO_AED, ZERO_AED, ZERO_AED)
    capped = min(conducted_minutes, scheduled_minutes)
    if capped >= PENALTY_THRESHOLD_MIN:
        full = aed(tutor_rate_aed)
        return PayrollComputation(prorated_aed=full, net_pay_aed=full, penalty_aed=ZERO_AED)
    # Compute net_pay from the *unquantized* prorated so the rounding matches
    # accounting_rules.md §4 + scripts/seed_dev_data.py (1820.83, not 1820.84).
    prorated_raw = Decimal(tutor_rate_aed) * Decimal(capped) / Decimal(scheduled_minutes)
    prorated = aed(prorated_raw)
    net_pay = aed(prorated_raw * PENALTY_FACTOR)
    penalty = aed(prorated - net_pay)
    return PayrollComputation(prorated, net_pay, penalty)


@dataclass(frozen=True)
class PayrollContext:
    session_id: str
    enrollment_id: int
    tutor_id: int
    posting_date: date
    fx_rate_aed_to_pkr: Decimal  # how many PKR for one AED on that day
    period: str


def build_accrual_draft(
    ctx: PayrollContext,
    comp: PayrollComputation,
) -> JournalEntryDraft | None:
    """Return None if the session has no tutor cost (zero-conducted / student-absent)."""
    if comp.prorated_aed == ZERO_AED:
        return None

    pkr_amount = aed(comp.net_pay_aed * Decimal(ctx.fx_rate_aed_to_pkr))
    lines = [
        JournalLineDraft(account_code="5010", debit_aed=comp.prorated_aed),
        JournalLineDraft(
            account_code="2020",
            credit_aed=comp.net_pay_aed,
            sub_ledger_keys={"tutor_id": ctx.tutor_id},
            original_currency="PKR",
            original_amount=pkr_amount,
            fx_rate=Decimal(ctx.fx_rate_aed_to_pkr),
        ),
    ]
    if comp.penalty_aed > ZERO_AED:
        lines.append(JournalLineDraft(account_code="5020", credit_aed=comp.penalty_aed))

    return JournalEntryDraft(
        date=ctx.posting_date,
        narration=f"Payroll accrual session={ctx.session_id} tutor={ctx.tutor_id}",
        source="system:payroll_agent",
        source_kind="system",
        source_ref=f"SES-{ctx.session_id}-COST",
        source_version="0.1",
        posted_by="system",
        lines=lines,
    )


def post_accrual(
    session,
    ctx: PayrollContext,
    comp: PayrollComputation,
    *,
    coa,
    sub_ledgers,
) -> PostedJournal | None:
    draft = build_accrual_draft(ctx, comp)
    if draft is None:
        return None
    return post_journal(session, draft, coa=coa, sub_ledgers=sub_ledgers)
