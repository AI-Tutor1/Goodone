"""Prepaid sub-ledger (1051 LMS, 1052 Other).

Both control accounts are debit-normal assets. Amortization debits an
expense (6310 LMS, ...) and credits 1051/1052; we mirror the credit side
into ``assets.prepaid_amortization_entries`` so each prepaid's
unamortized balance is recoverable.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from src.core.money import ZERO_AED, aed
from src.ledger.coa import SubLedgerName
from src.ledger.subledger import ReconciliationResult, signed_delta

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.ledger.posting import JournalLineDraft


_PREPAID_ACCOUNTS = ("1051", "1052")


class PrepaidSubLedger:
    name: SubLedgerName = SubLedgerName.PREPAID
    control_accounts: tuple[str, ...] = _PREPAID_ACCOUNTS
    key_field: str = "prepaid_id"

    def apply_line(
        self,
        session: Session,
        *,
        je_id: int,
        line_id: int,
        period: str,
        effective_date: date,
        line: JournalLineDraft,
    ) -> None:
        prepaid_id = int(line.sub_ledger_keys["prepaid_id"])
        # Prepaid is debit-normal; a credit on 1051/1052 means amortization.
        delta = signed_delta(line, side="debit")  # signed delta to the asset
        if delta >= ZERO_AED:
            # Top-up of a prepaid (debit) is recorded by the seed script directly
            # in assets.prepaids.total_aed; we only mirror the amortization side.
            return
        amount = -delta  # positive amortization amount
        session.execute(
            text(
                """
                INSERT INTO assets.prepaid_amortization_entries (
                    prepaid_id, je_id, line_id, period, monthly_amount_aed
                ) VALUES (
                    :prepaid_id, :je_id, :line_id, :period, :amount
                )
                """,
            ),
            {
                "prepaid_id": prepaid_id,
                "je_id": je_id,
                "line_id": line_id,
                "period": period,
                "amount": amount,
            },
        )

    def row_exists(self, session: Session, key: str | int) -> bool:
        return bool(
            session.execute(
                text("SELECT 1 FROM assets.prepaids WHERE prepaid_id = :id"),
                {"id": int(key)},
            ).scalar(),
        )

    def balance(
        self,
        session: Session,
        key: str | int,
        *,
        as_of: date | None = None,
    ) -> Decimal:
        row = session.execute(
            text("SELECT total_aed FROM assets.prepaids WHERE prepaid_id = :id"),
            {"id": int(key)},
        ).one_or_none()
        if row is None:
            return ZERO_AED
        amortized = session.execute(
            text(
                "SELECT COALESCE(SUM(monthly_amount_aed), 0) "
                "FROM assets.prepaid_amortization_entries "
                "WHERE prepaid_id = :id",
            ),
            {"id": int(key)},
        ).scalar_one()
        return aed(row.total_aed) - aed(amortized)

    def reconcile_to_gl(
        self,
        session: Session,
        *,
        as_of: date | None = None,
    ) -> ReconciliationResult:
        gl_balance = aed(
            session.execute(
                text(
                    "SELECT COALESCE(SUM(jl.debit_aed - jl.credit_aed), 0) "
                    "FROM ledger.journal_lines jl "
                    "JOIN ledger.journal_entries je ON je.je_id = jl.je_id "
                    "WHERE jl.account_code = ANY(:codes) "
                    "AND (CAST(:as_of AS date) IS NULL OR je.date <= CAST(:as_of AS date))",
                ),
                {"codes": list(_PREPAID_ACCOUNTS), "as_of": as_of},
            ).scalar_one(),
        )
        # Sub-ledger sum = sum of (total_aed) − sum of amortization entries.
        total = aed(
            session.execute(
                text("SELECT COALESCE(SUM(total_aed), 0) FROM assets.prepaids"),
            ).scalar_one(),
        )
        amort = aed(
            session.execute(
                text(
                    "SELECT COALESCE(SUM(monthly_amount_aed), 0) "
                    "FROM assets.prepaid_amortization_entries",
                ),
            ).scalar_one(),
        )
        sub_sum = total - amort
        diff = gl_balance - sub_sum
        return ReconciliationResult(
            sub_ledger="prepaid",
            matches=(diff == ZERO_AED),
            gl_balance=gl_balance,
            sub_ledger_sum=sub_sum,
            diff=diff,
            per_key_diffs={},
        )
