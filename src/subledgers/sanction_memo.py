"""Sanction memo sub-ledger (paired accounts 2060 and 9010).

Per ``docs/accounting_rules.md`` §13–14 (revised), sanction memos use the
paired-account model:

* Approval (§13): ``Dr 2060 (COMMIT) / Cr 9010 (CONTRA)``
* Spend (§14a): ``Dr 9010 (SPEND_REVERSE) / Cr 2060 (SPEND_REVERSE)``

The 9xxx range is excluded from BS / IS roll-ups by the Reporting Agent;
the sub-ledger entry's ``side`` field discriminates COMMIT / CONTRA /
SPEND_REVERSE for management reporting.
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


class SanctionMemoSubLedger:
    name = SubLedgerName.SANCTION_MEMO
    control_accounts = ("2060", "9010")
    key_field = "sanction_request_id"

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
        request_id = int(line.sub_ledger_keys["sanction_request_id"])
        side = _classify(line)
        delta = signed_delta(line, side="credit")  # 2060 is credit-normal
        session.execute(
            text(
                """
                INSERT INTO subledger.sanction_memo_entries (
                    sanction_request_id, je_id, line_id, period,
                    effective_date, side, delta_aed
                ) VALUES (
                    :request_id, :je_id, :line_id, :period,
                    :effective_date,
                    CAST(:side AS subledger.sanction_memo_side),
                    :delta
                )
                """,
            ),
            {
                "request_id": request_id,
                "je_id": je_id,
                "line_id": line_id,
                "period": period,
                "effective_date": effective_date,
                "side": side,
                "delta": delta,
            },
        )

    def row_exists(self, session: Session, key: str | int) -> bool:
        return bool(
            session.execute(
                text(
                    "SELECT 1 FROM sanctions.sanction_requests WHERE id = :id",
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
        """Open commitment per request = SUM(COMMIT) − SUM(SPEND_REVERSE) on 2060."""
        return aed(
            session.execute(
                text(
                    """
                    SELECT COALESCE(SUM(
                        CASE side
                            WHEN 'COMMIT'         THEN delta_aed
                            WHEN 'SPEND_REVERSE'  THEN -delta_aed
                            ELSE 0
                        END
                    ), 0)
                    FROM subledger.sanction_memo_entries
                    WHERE sanction_request_id = :id
                    """,
                ),
                {"id": int(key)},
            ).scalar_one(),
        )

    def reconcile_to_gl(
        self,
        session: Session,
        *,
        as_of: date | None = None,
    ) -> ReconciliationResult:
        # 2060 is credit-normal (liability). Reconcile its GL balance to the
        # COMMIT − SPEND_REVERSE half of the sub-ledger.
        gl_balance = aed(
            session.execute(
                text(
                    "SELECT COALESCE(SUM(jl.credit_aed - jl.debit_aed), 0) "
                    "FROM ledger.journal_lines jl "
                    "JOIN ledger.journal_entries je ON je.je_id = jl.je_id "
                    "WHERE jl.account_code = '2060'",
                ),
            ).scalar_one(),
        )
        sub_sum = aed(
            session.execute(
                text(
                    """
                    SELECT COALESCE(SUM(
                        CASE side
                            WHEN 'COMMIT'         THEN delta_aed
                            WHEN 'SPEND_REVERSE'  THEN -delta_aed
                            ELSE 0
                        END
                    ), 0) FROM subledger.sanction_memo_entries
                    """,
                ),
            ).scalar_one(),
        )
        diff = gl_balance - sub_sum
        return ReconciliationResult(
            sub_ledger="sanction_memo",
            matches=(diff == ZERO_AED),
            gl_balance=gl_balance,
            sub_ledger_sum=sub_sum,
            diff=diff,
            per_key_diffs={},
        )


def _classify(line: JournalLineDraft) -> str:
    """Map an account+sign onto COMMIT / CONTRA / SPEND_REVERSE.

    Approval JE: Dr 2060 (COMMIT) / Cr 9010 (CONTRA).
    Spend JE:    Dr 9010 (SPEND_REVERSE) / Cr 2060 (SPEND_REVERSE).
    """
    code = line.account_code
    is_debit = aed(line.debit_aed) > ZERO_AED
    if code == "2060" and is_debit:
        return "COMMIT"
    if code == "9010" and not is_debit:
        return "CONTRA"
    if code == "9010" and is_debit:
        return "SPEND_REVERSE"
    if code == "2060" and not is_debit:
        return "SPEND_REVERSE"
    return "COMMIT"  # fallback; CHECK constraint will surface mistakes
