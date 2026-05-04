"""Period state machine.

Per ``docs/rules/period_close_rules.md`` the lifecycle is:

    OPEN ──> IN_CLOSING ──> CLOSED
                              ^
                              │
                              └── REOPENED <─── (CFO reopen with reason ≥ 30)

Phase 2's :func:`close` runs the *always-required* checks only —
sub-ledger reconciliation, trial balance, attachment-policy gate — and
takes a snapshot. The Phase-4 agents (depreciation / amortization / FX
revaluation) are not invoked here; that wiring lands when the Period
Close Agent ships.

TODO Phase 4: invoke depreciation, amortization, FX revaluation, and
prepaid roll-forward as part of ``close()`` before the reconciliation
gate, per ``period_close_rules.md`` §2.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from src.core.exceptions import (
    LedgerError,
    PeriodError,
    PeriodNotFoundError,
    PeriodReopenReasonError,
    ReconciliationMismatchError,
)
from src.core.money import aed

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.ledger.subledger import SubLedgerRegistry


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CloseResult:
    period: str
    closed_at: datetime
    closed_by: str
    gl_balance: Decimal
    sub_ledger_snapshots: dict[str, Decimal]
    je_count: int
    je_total_debit: Decimal


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


@dataclass
class PeriodService:
    """Period lifecycle operations.

    Stateless; all data lives in ``master.periods`` and ``audit.period_close_log``.
    """

    sub_ledgers: SubLedgerRegistry | None = None

    # ---- query helpers ----------------------------------------------------

    def status(self, session: Session, period: str) -> str:
        row = session.execute(
            text("SELECT status FROM master.periods WHERE period = :p"),
            {"p": period},
        ).one_or_none()
        if row is None:
            raise PeriodNotFoundError(message=f"period {period} not found", period=period)
        return str(row.status)

    def ensure_period(self, session: Session, period: str) -> None:
        """Create the period in OPEN state if it doesn't exist (idempotent)."""
        _validate_period_format(period)
        session.execute(
            text(
                "INSERT INTO master.periods (period, status, opened_at) "
                "VALUES (:p, 'OPEN', NOW()) "
                "ON CONFLICT (period) DO NOTHING",
            ),
            {"p": period},
        )

    # ---- transitions ------------------------------------------------------

    def begin_closing(self, session: Session, period: str, *, by: str) -> None:
        """OPEN → IN_CLOSING."""
        current = self.status(session, period)
        if current != "OPEN":
            raise PeriodError(
                message=f"cannot begin_closing from {current}",
                period=period,
                context={"current": current},
            )
        session.execute(
            text(
                "UPDATE master.periods SET status = 'IN_CLOSING' WHERE period = :p",
            ),
            {"p": period},
        )
        _audit_period_action(session, period, action="BEGIN_CLOSING", actor=by)

    def close(
        self,
        session: Session,
        period: str,
        *,
        by: str,
    ) -> CloseResult:
        """Run the Phase-2 close gate and lock the period.

        Hard-fails if any sub-ledger does not reconcile, the trial balance
        is non-zero, or any flagged-large JE lacks an attachment.
        """
        current = self.status(session, period)
        if current not in {"OPEN", "IN_CLOSING", "REOPENED"}:
            raise PeriodError(
                message=f"cannot close from {current}",
                period=period,
                context={"current": current},
            )

        # 1) Trial balance for this period.
        debit_total, credit_total, je_count = _trial_balance_for_period(session, period)
        if debit_total != credit_total:
            raise PeriodError(
                message=f"trial balance off: dr={debit_total} cr={credit_total}",
                period=period,
                context={"debit": str(debit_total), "credit": str(credit_total)},
            )

        # 2) Attachment-policy gate for this period.
        offenders = (
            session.execute(
                text(
                    "SELECT je_id FROM ledger.journal_entries "
                    "WHERE period = :p AND attachment_required "
                    "AND attachment_url IS NULL "
                    "AND attachment_override_reason IS NULL",
                ),
                {"p": period},
            )
            .scalars()
            .all()
        )
        if offenders:
            raise PeriodError(
                message=(
                    f"period {period} cannot close: {len(offenders)} flagged JE(s) "
                    "lack attachment and override reason"
                ),
                period=period,
                context={"je_ids": list(offenders)},
            )

        # 3) Sub-ledger reconciliation (every registered sub-ledger).
        sl_snapshots: dict[str, Decimal] = {}
        if self.sub_ledgers is not None:
            for sl in self.sub_ledgers.all():
                result = sl.reconcile_to_gl(session)
                sl_snapshots[sl.name.value] = result.sub_ledger_sum
                if not result.matches:
                    raise ReconciliationMismatchError(
                        message=(
                            f"sub_ledger {result.sub_ledger} does not reconcile "
                            f"(gl={result.gl_balance}, sub={result.sub_ledger_sum})"
                        ),
                        sub_ledger=result.sub_ledger,
                        account_code=",".join(sl.control_accounts),
                        gl_balance=result.gl_balance,
                        sub_ledger_sum=result.sub_ledger_sum,
                    )

        # 4) Snapshot + lock.
        gl_snapshot = _gl_balances_snapshot(session, period)
        snapshot_payload = json.dumps(
            {k: str(v) for k, v in gl_snapshot.items()},
            sort_keys=True,
        )
        sl_payload = json.dumps(
            {k: str(v) for k, v in sl_snapshots.items()},
            sort_keys=True,
        )
        metrics_payload = json.dumps(
            {
                "je_count": je_count,
                "trial_debit_total": str(debit_total),
                "trial_credit_total": str(credit_total),
            },
        )
        session.execute(
            text(
                """
                INSERT INTO audit.period_close_log (
                    period, action, actor, ts, reason,
                    gl_balances_snapshot, sub_ledger_balances_snapshot,
                    summary_metrics
                ) VALUES (
                    :p, 'CLOSE', :actor, NOW(), NULL,
                    CAST(:gl AS jsonb),
                    CAST(:sl AS jsonb),
                    CAST(:m  AS jsonb)
                )
                """,
            ),
            {
                "p": period,
                "actor": by,
                "gl": snapshot_payload,
                "sl": sl_payload,
                "m": metrics_payload,
            },
        )
        closed_at = session.execute(
            text(
                "UPDATE master.periods SET status='CLOSED', closed_at=NOW(), "
                "closed_by=:by WHERE period=:p RETURNING closed_at",
            ),
            {"p": period, "by": by},
        ).scalar_one()
        _audit_period_action(session, period, action="CLOSE_PERIOD", actor=by)

        return CloseResult(
            period=period,
            closed_at=closed_at,
            closed_by=by,
            gl_balance=debit_total,
            sub_ledger_snapshots=sl_snapshots,
            je_count=je_count,
            je_total_debit=debit_total,
        )

    def reopen(
        self,
        session: Session,
        period: str,
        *,
        by: str,
        reason: str,
    ) -> None:
        """CLOSED → REOPENED. Reason ≥ 30 chars required."""
        if len(reason.strip()) < 30:
            raise PeriodReopenReasonError(
                message="reopen reason must be at least 30 characters",
                period=period,
                context={"reason_length": len(reason.strip())},
            )
        current = self.status(session, period)
        if current != "CLOSED":
            raise PeriodError(
                message=f"cannot reopen from {current}",
                period=period,
                context={"current": current},
            )
        session.execute(
            text(
                "UPDATE master.periods SET status='REOPENED', "
                "reopened_at=NOW(), reopened_by=:by WHERE period=:p",
            ),
            {"p": period, "by": by},
        )
        session.execute(
            text(
                "INSERT INTO audit.period_close_log "
                "(period, action, actor, ts, reason) "
                "VALUES (:p, 'REOPEN', :by, NOW(), :reason)",
            ),
            {"p": period, "by": by, "reason": reason},
        )
        _audit_period_action(session, period, action="REOPEN_PERIOD", actor=by)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_period_format(period: str) -> None:
    if len(period) != 7 or period[4] != "-" or not period[:4].isdigit() or not period[5:].isdigit():
        raise PeriodError(message=f"bad period format '{period}', want YYYY-MM", period=period)
    month = int(period[5:])
    if not (1 <= month <= 12):
        raise PeriodError(message=f"bad month in period '{period}'", period=period)


def _trial_balance_for_period(
    session: Session,
    period: str,
) -> tuple[Decimal, Decimal, int]:
    row = session.execute(
        text(
            "SELECT "
            "  COALESCE(SUM(total_debit_aed), 0) AS d, "
            "  COALESCE(SUM(total_credit_aed), 0) AS c, "
            "  COUNT(*) AS n "
            "FROM ledger.journal_entries WHERE period = :p AND status = 'POSTED'",
        ),
        {"p": period},
    ).one()
    return aed(row.d), aed(row.c), int(row.n)


def _gl_balances_snapshot(
    session: Session,
    period: str,
) -> dict[str, Decimal]:
    """Per-account net balance for the period (debits − credits)."""
    rows = session.execute(
        text(
            "SELECT jl.account_code, "
            "       COALESCE(SUM(jl.debit_aed - jl.credit_aed), 0) AS bal "
            "FROM ledger.journal_lines jl "
            "JOIN ledger.journal_entries je ON je.je_id = jl.je_id "
            "WHERE je.period = :p AND je.status = 'POSTED' "
            "GROUP BY jl.account_code "
            "ORDER BY jl.account_code",
        ),
        {"p": period},
    ).all()
    return {row.account_code: aed(row.bal) for row in rows}


def _audit_period_action(
    session: Session,
    period: str,
    *,
    action: str,
    actor: str,
) -> None:
    session.execute(
        text(
            "INSERT INTO audit.audit_log "
            "(ts, actor, action, target_type, target_id, success) "
            "VALUES (NOW(), :actor, CAST(:action AS audit.audit_action), "
            "        'period', :period, true)",
        ),
        {"actor": actor, "action": action, "period": period},
    )


# ---------------------------------------------------------------------------
# Iteration helper (used by the seed script)
# ---------------------------------------------------------------------------


@dataclass
class PeriodRange:
    start: str
    end: str
    members: list[str] = field(default_factory=list)


def iter_months(start: str, end: str) -> Iterator[str]:
    """Yield YYYY-MM strings inclusive of both endpoints."""
    sy, sm = (int(x) for x in start.split("-"))
    ey, em = (int(x) for x in end.split("-"))
    y, m = sy, sm
    while (y, m) <= (ey, em):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m == 13:
            m = 1
            y += 1


# Re-exported for callers; keeps the names available without an `import *`.
__all__ = [
    "CloseResult",
    "LedgerError",
    "PeriodService",
    "iter_months",
]
_ = date  # silence "unused" until someone imports this directly
