"""Intangible sub-ledger (1121 in-development, 1122 launched, 1123 accum amort).

The Tuitional AI capitalisation runs each month while the asset is
``IN_DEVELOPMENT``. After launch the carrying value is reclassified to 1122
and amortised over 60 months (per ``docs/context.md`` §9).
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


_INTANGIBLE_ACCOUNTS = ("1121", "1122")
_ACCUM_AMORT = ("1123",)


class IntangibleSubLedger:
    name = SubLedgerName.INTANGIBLE
    control_accounts = _INTANGIBLE_ACCOUNTS + _ACCUM_AMORT
    key_field = "intangible_id"

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
        intangible_id = int(line.sub_ledger_keys["intangible_id"])
        entry_type, delta = _classify(line)
        if delta == ZERO_AED:
            return
        session.execute(
            text(
                """
                INSERT INTO assets.intangible_entries (
                    intangible_id, je_id, line_id, period, type, delta_aed
                ) VALUES (
                    :intangible_id, :je_id, :line_id, :period,
                    CAST(:type AS assets.intangible_entry_type),
                    :delta
                )
                """,
            ),
            {
                "intangible_id": intangible_id,
                "je_id": je_id,
                "line_id": line_id,
                "period": period,
                "type": entry_type,
                "delta": delta,
            },
        )

    def row_exists(self, session: Session, key: str | int) -> bool:
        return bool(
            session.execute(
                text(
                    "SELECT 1 FROM assets.intangibles WHERE intangible_id = :id",
                ),
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
        # Net carrying value = capitalised + reclassed − amortised.
        rows = session.execute(
            text(
                "SELECT type, COALESCE(SUM(delta_aed), 0) AS s "
                "FROM assets.intangible_entries WHERE intangible_id = :id "
                "GROUP BY type",
            ),
            {"id": int(key)},
        ).all()
        capitalised = ZERO_AED
        amortised = ZERO_AED
        for row in rows:
            v = aed(row.s)
            if row.type == "AMORTIZE":
                amortised += v
            else:
                capitalised += v
        return capitalised - amortised

    def reconcile_to_gl(
        self,
        session: Session,
        *,
        as_of: date | None = None,
    ) -> ReconciliationResult:
        gl_intangible_cost = aed(
            session.execute(
                text(
                    "SELECT COALESCE(SUM(jl.debit_aed - jl.credit_aed), 0) "
                    "FROM ledger.journal_lines jl "
                    "JOIN ledger.journal_entries je ON je.je_id = jl.je_id "
                    "WHERE jl.account_code = ANY(:codes)",
                ),
                {"codes": list(_INTANGIBLE_ACCOUNTS)},
            ).scalar_one(),
        )
        gl_amort = aed(
            session.execute(
                text(
                    "SELECT COALESCE(SUM(jl.credit_aed - jl.debit_aed), 0) "
                    "FROM ledger.journal_lines jl "
                    "JOIN ledger.journal_entries je ON je.je_id = jl.je_id "
                    "WHERE jl.account_code = ANY(:codes)",
                ),
                {"codes": list(_ACCUM_AMORT)},
            ).scalar_one(),
        )
        gl_nbv = gl_intangible_cost - gl_amort

        sub_sum = aed(
            session.execute(
                text(
                    "SELECT COALESCE(SUM(CASE WHEN type='AMORTIZE' "
                    "THEN -delta_aed ELSE delta_aed END), 0) "
                    "FROM assets.intangible_entries",
                ),
            ).scalar_one(),
        )
        diff = gl_nbv - sub_sum
        return ReconciliationResult(
            sub_ledger="intangible",
            matches=(diff == ZERO_AED),
            gl_balance=gl_nbv,
            sub_ledger_sum=sub_sum,
            diff=diff,
            per_key_diffs={},
        )


def _classify(line: JournalLineDraft) -> tuple[str, Decimal]:
    code = line.account_code
    if code == "1121":
        return "CAPITALIZE", signed_delta(line, side="debit")
    if code == "1122":
        # Reclassification (Dr 1122 / Cr 1121 on the launch JE)
        return "RECLASS_TO_LAUNCHED", signed_delta(line, side="debit")
    if code == "1123":
        # Accumulated amortisation: a credit grows it, signed positive.
        return "AMORTIZE", signed_delta(line, side="credit")
    return "CAPITALIZE", ZERO_AED
