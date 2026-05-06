"""Tutor-payable sub-ledger (control accounts 2020 PKR, 2030 AED).

Both control accounts are credit-normal liabilities. PKR-denominated
tutors track ``original_currency='PKR'`` + ``original_amount`` +
``fx_rate_at_accrual`` per row so the FX agent (Phase 4) can revalue and
realise gain/loss.
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


_CONTROL_ACCOUNTS = ("2020", "2030")


class TutorPayableSubLedger:
    name: SubLedgerName = SubLedgerName.TUTOR_PAYABLE
    control_accounts: tuple[str, ...] = _CONTROL_ACCOUNTS
    key_field: str = "tutor_id"

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
        tutor_id = int(line.sub_ledger_keys["tutor_id"])
        delta = signed_delta(line, side="credit")
        currency = line.original_currency or ("PKR" if line.account_code == "2020" else "AED")
        original = (
            line.original_amount
            if line.original_amount is not None
            else aed(
                line.credit_aed - line.debit_aed,
            )
        )
        rate = line.fx_rate if line.fx_rate is not None else Decimal("1.00000000")
        session.execute(
            text(
                """
                INSERT INTO subledger.tutor_payable_entries (
                    tutor_id, je_id, line_id, period, effective_date,
                    delta_aed, original_currency, original_amount,
                    fx_rate_at_accrual
                ) VALUES (
                    :tutor_id, :je_id, :line_id, :period, :effective_date,
                    :delta_aed, :currency, :original, :rate
                )
                """,
            ),
            {
                "tutor_id": tutor_id,
                "je_id": je_id,
                "line_id": line_id,
                "period": period,
                "effective_date": effective_date,
                "delta_aed": delta,
                "currency": currency,
                "original": original,
                "rate": rate,
            },
        )

    def row_exists(self, session: Session, key: str | int) -> bool:
        return bool(
            session.execute(
                text(
                    "SELECT 1 FROM master.tutors WHERE tutor_id = :tid AND active = true",
                ),
                {"tid": int(key)},
            ).scalar(),
        )

    def balance(
        self,
        session: Session,
        key: str | int,
        *,
        as_of: date | None = None,
    ) -> Decimal:
        sql = (
            "SELECT COALESCE(SUM(delta_aed), 0) "
            "FROM subledger.tutor_payable_entries "
            "WHERE tutor_id = :tid"
        )
        params: dict[str, object] = {"tid": int(key)}
        if as_of is not None:
            sql += " AND effective_date <= :as_of"
            params["as_of"] = as_of
        return aed(session.execute(text(sql), params).scalar_one())

    def reconcile_to_gl(
        self,
        session: Session,
        *,
        as_of: date | None = None,
    ) -> ReconciliationResult:
        gl_balance = _credit_normal_control_balance(
            session,
            _CONTROL_ACCOUNTS,
            as_of=as_of,
        )
        sub_sum = aed(
            session.execute(
                text(
                    "SELECT COALESCE(SUM(delta_aed), 0) "
                    "FROM subledger.tutor_payable_entries "
                    "WHERE (CAST(:as_of AS date) IS NULL "
                    "OR effective_date <= CAST(:as_of AS date))",
                ),
                {"as_of": as_of},
            ).scalar_one(),
        )
        per_key = {
            str(row.tutor_id): aed(row.delta)
            for row in session.execute(
                text(
                    "SELECT tutor_id, COALESCE(SUM(delta_aed), 0) AS delta "
                    "FROM subledger.tutor_payable_entries "
                    "WHERE (CAST(:as_of AS date) IS NULL "
                    "OR effective_date <= CAST(:as_of AS date)) "
                    "GROUP BY tutor_id",
                ),
                {"as_of": as_of},
            ).all()
        }
        diff = gl_balance - sub_sum
        return ReconciliationResult(
            sub_ledger="tutor_payable",
            matches=(diff == ZERO_AED),
            gl_balance=gl_balance,
            sub_ledger_sum=sub_sum,
            diff=diff,
            per_key_diffs=per_key,
        )


def _credit_normal_control_balance(
    session: Session,
    codes: tuple[str, ...],
    *,
    as_of: date | None,
) -> Decimal:
    sql = (
        "SELECT COALESCE(SUM(jl.credit_aed - jl.debit_aed), 0) "
        "FROM ledger.journal_lines jl "
        "JOIN ledger.journal_entries je ON je.je_id = jl.je_id "
        "WHERE jl.account_code = ANY(:codes) "
    )
    params: dict[str, object] = {"codes": list(codes)}
    if as_of is not None:
        sql += "AND je.date <= :as_of "
        params["as_of"] = as_of
    return aed(session.execute(text(sql), params).scalar_one())
