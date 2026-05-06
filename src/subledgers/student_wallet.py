"""Student wallet sub-ledger (control account 2050).

Wallet balance is *credit-normal* (it's a liability). Top-ups credit 2050
and grow the wallet; consumption / refunds debit 2050 and shrink it. The
DB has a deferred AFTER trigger that hard-stops any sequence pushing a
per-student balance below zero.
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


class StudentWalletSubLedger:
    name: SubLedgerName = SubLedgerName.STUDENT_WALLET
    control_accounts: tuple[str, ...] = ("2050",)
    key_field: str = "student_id"

    # ---- protocol methods -------------------------------------------------

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
        student_id = int(line.sub_ledger_keys["student_id"])
        delta = signed_delta(line, side="credit")
        entry_type = _classify(line)
        session.execute(
            text(
                """
                INSERT INTO subledger.student_wallet_entries (
                    student_id, je_id, line_id, period, effective_date,
                    delta_aed, type
                ) VALUES (
                    :student_id, :je_id, :line_id, :period, :effective_date,
                    :delta_aed, CAST(:type AS wallet_entry_type)
                )
                """,
            ),
            {
                "student_id": student_id,
                "je_id": je_id,
                "line_id": line_id,
                "period": period,
                "effective_date": effective_date,
                "delta_aed": delta,
                "type": entry_type,
            },
        )

    def row_exists(self, session: Session, key: str | int) -> bool:
        return bool(
            session.execute(
                text(
                    "SELECT 1 FROM master.students WHERE student_id = :sid AND active = true",
                ),
                {"sid": int(key)},
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
            "FROM subledger.student_wallet_entries "
            "WHERE student_id = :sid"
        )
        params: dict[str, object] = {"sid": int(key)}
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
        gl_balance = _control_balance(session, "2050", as_of=as_of)
        sub_sum = aed(
            session.execute(
                text(
                    "SELECT COALESCE(SUM(delta_aed), 0) "
                    "FROM subledger.student_wallet_entries "
                    "WHERE (CAST(:as_of AS date) IS NULL "
                    "OR effective_date <= CAST(:as_of AS date))",
                ),
                {"as_of": as_of},
            ).scalar_one(),
        )
        per_key = {
            str(row.student_id): aed(row.delta)
            for row in session.execute(
                text(
                    "SELECT student_id, COALESCE(SUM(delta_aed), 0) AS delta "
                    "FROM subledger.student_wallet_entries "
                    "WHERE (CAST(:as_of AS date) IS NULL "
                    "OR effective_date <= CAST(:as_of AS date)) "
                    "GROUP BY student_id",
                ),
                {"as_of": as_of},
            ).all()
        }
        diff = gl_balance - sub_sum
        return ReconciliationResult(
            sub_ledger="student_wallet",
            matches=(diff == ZERO_AED),
            gl_balance=gl_balance,
            sub_ledger_sum=sub_sum,
            diff=diff,
            per_key_diffs=per_key,
        )


# ---------------------------------------------------------------------------


def _classify(line: JournalLineDraft) -> str:
    """Map a 2050 line to a wallet_entry_type for reporting clarity.

    The contra account on the JE is what tells us whether this is a
    top-up, consumption (revenue), or refund. We sniff the first
    non-2050 line on the same draft when it's available; otherwise we
    fall back to the sign of the delta.
    """
    # We don't have the full draft here — just one line. The agent / caller
    # can override by passing an explicit type via dimensions['wallet_type'];
    # otherwise infer from sign.
    explicit = line.dimensions.get("wallet_type")
    if explicit in {"TOPUP", "CONSUME", "REFUND", "ADJUST"}:
        return str(explicit)
    delta = signed_delta(line, side="credit")
    if delta > ZERO_AED:
        return "TOPUP"
    if delta < ZERO_AED:
        return "CONSUME"
    return "ADJUST"


def _control_balance(
    session: Session,
    account_code: str,
    *,
    as_of: date | None,
) -> Decimal:
    """GL balance for a credit-normal control account (credit − debit)."""
    sql = (
        "SELECT COALESCE(SUM(jl.credit_aed - jl.debit_aed), 0) "
        "FROM ledger.journal_lines jl "
        "JOIN ledger.journal_entries je ON je.je_id = jl.je_id "
        "WHERE jl.account_code = :code "
    )
    params: dict[str, object] = {"code": account_code}
    if as_of is not None:
        sql += "AND je.date <= :as_of "
        params["as_of"] = as_of
    return aed(session.execute(text(sql), params).scalar_one())
