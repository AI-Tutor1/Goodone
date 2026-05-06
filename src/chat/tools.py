"""Read-only GL tools the chat agent can call.

Each tool is a thin wrapper that runs a parameterised SQL ``SELECT`` (or
delegates to the existing reporting/agent layer). **No tool here ever
writes to the ledger.** The wrapper functions return JSON-serialisable
dicts so the LLM can quote them back to the user.

The set of tools is intentionally small — the goal is to answer the
day-to-day CFO questions ("what's my AR?", "did April close?", "any
sanctions waiting on me?") without giving the LLM an open SQL prompt.

Adding a tool: append a ``Tool`` to ``BUILTIN_TOOLS`` and a matching
JSON Schema to ``input_schema``. The chat service auto-discovers the
descriptor.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import text

from src.agents import reporting
from src.chat.models import ToolDescriptor

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Tool runtime types
# ---------------------------------------------------------------------------


ToolFn = Callable[["Session", dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class Tool:
    """A read-only GL query the chat agent can invoke."""

    name: str
    description: str
    input_schema: dict[str, Any]
    fn: ToolFn

    def descriptor(self) -> ToolDescriptor:
        return ToolDescriptor(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decimal_to_str(obj: Any) -> Any:
    """Recursively convert Decimal → str so dicts stay JSON-friendly.

    Avoids serialiser surprises when the chat API streams the tool result
    back to the frontend.
    """
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_str(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_str(x) for x in obj]
    return obj


# ---------------------------------------------------------------------------
# Concrete tools
# ---------------------------------------------------------------------------


def _get_account_balance(session: Session, args: dict[str, Any]) -> dict[str, Any]:
    code = str(args["account_code"])
    as_of = args.get("as_of")
    sql = (
        "SELECT COALESCE(SUM(jl.debit_aed), 0)  AS dr, "
        "       COALESCE(SUM(jl.credit_aed), 0) AS cr, "
        "       COALESCE(SUM(jl.debit_aed - jl.credit_aed), 0) AS net_dr "
        "FROM   ledger.journal_lines jl "
        "JOIN   ledger.journal_entries je ON je.je_id = jl.je_id "
        "WHERE  jl.account_code = :code "
        "  AND  je.status = 'POSTED' "
        "  AND  (CAST(:as_of AS date) IS NULL OR je.effective_date <= CAST(:as_of AS date))"
    )
    row = session.execute(text(sql), {"code": code, "as_of": as_of}).one()
    return cast(
        dict[str, Any],
        _decimal_to_str(
            {
                "account_code": code,
                "as_of": as_of,
                "debit_total": row.dr,
                "credit_total": row.cr,
                "net_debit": row.net_dr,
            }
        ),
    )


def _get_pnl(session: Session, args: dict[str, Any]) -> dict[str, Any]:
    period = str(args["period"])
    pnl = reporting.profit_and_loss(session, period=period)
    return cast(
        dict[str, Any],
        _decimal_to_str(
            {
                "period": pnl.period,
                "revenue_total": pnl.revenue_total,
                "cost_total": pnl.cost_total,
                "gross_profit": pnl.gross_profit,
                "opex_total": pnl.opex_total,
                "operating_profit": pnl.operating_profit,
                "non_op_total": pnl.non_op_total,
                "net_profit": pnl.net_profit,
            }
        ),
    )


def _get_trial_balance(session: Session, args: dict[str, Any]) -> dict[str, Any]:
    period = args.get("period")
    sql = (
        "SELECT COALESCE(SUM(jl.debit_aed), 0)  AS total_dr, "
        "       COALESCE(SUM(jl.credit_aed), 0) AS total_cr "
        "FROM   ledger.journal_lines jl "
        "JOIN   ledger.journal_entries je ON je.je_id = jl.je_id "
        "WHERE  je.status = 'POSTED' "
        "  AND  (CAST(:p AS text) IS NULL OR je.period = :p)"
    )
    row = session.execute(text(sql), {"p": str(period) if period else None}).one()
    diff = row.total_dr - row.total_cr
    return cast(
        dict[str, Any],
        _decimal_to_str(
            {
                "period": period,
                "total_debit": row.total_dr,
                "total_credit": row.total_cr,
                "difference": diff,
                "balanced": diff == 0,
            }
        ),
    )


def _get_period_status(session: Session, args: dict[str, Any]) -> dict[str, Any]:
    period = str(args["period"])
    row = session.execute(
        text(
            """
            SELECT period, status::text AS status, closed_at, closed_by, reopen_reason
            FROM   ledger.periods
            WHERE  period = :p
            """,
        ),
        {"p": period},
    ).first()
    if row is None:
        return {"period": period, "status": "NEVER_OPENED"}
    return {
        "period": row.period,
        "status": row.status,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "closed_by": row.closed_by,
        "reopen_reason": row.reopen_reason,
    }


def _list_open_sanctions(session: Session, _args: dict[str, Any]) -> dict[str, Any]:
    rows = session.execute(
        text(
            """
            SELECT sr.id, sr.requested_by, sr.amount_aed,
                   sr.status::text AS status, sr.created_at, sr.purpose
            FROM   sanctions.sanction_requests sr
            WHERE  sr.status IN ('PENDING_FA', 'PENDING_CFO')
            ORDER  BY sr.created_at ASC
            LIMIT  50
            """,
        ),
    ).all()
    return cast(
        dict[str, Any],
        _decimal_to_str(
            {
                "count": len(rows),
                "requests": [
                    {
                        "id": str(r.id),
                        "requested_by": r.requested_by,
                        "amount_aed": r.amount_aed,
                        "status": r.status,
                        "purpose": r.purpose,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in rows
                ],
            }
        ),
    )


def _list_quarantine(session: Session, _args: dict[str, Any]) -> dict[str, Any]:
    rows = session.execute(
        text(
            """
            SELECT id, source_kind, rule_id, severity::text AS severity,
                   resolved, created_at
            FROM   staging.data_quality_quarantine
            WHERE  resolved = false
            ORDER  BY created_at DESC
            LIMIT  50
            """,
        ),
    ).all()
    return {
        "count": len(rows),
        "items": [
            {
                "id": str(r.id),
                "source_kind": r.source_kind,
                "rule_id": r.rule_id,
                "severity": r.severity,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


def _list_recent_journals(session: Session, args: dict[str, Any]) -> dict[str, Any]:
    limit = min(int(args.get("limit", 20)), 100)
    rows = session.execute(
        text(
            """
            SELECT je.je_id, je.effective_date, je.period, je.source_kind,
                   je.narration, je.total_aed, je.posted_at
            FROM   ledger.journal_entries je
            WHERE  je.status = 'POSTED'
            ORDER  BY je.posted_at DESC
            LIMIT  :n
            """,
        ),
        {"n": limit},
    ).all()
    return cast(
        dict[str, Any],
        _decimal_to_str(
            {
                "count": len(rows),
                "journals": [
                    {
                        "je_id": str(r.je_id),
                        "effective_date": r.effective_date.isoformat()
                        if r.effective_date
                        else None,
                        "period": r.period,
                        "source_kind": r.source_kind,
                        "narration": r.narration,
                        "total_aed": r.total_aed,
                        "posted_at": r.posted_at.isoformat() if r.posted_at else None,
                    }
                    for r in rows
                ],
            }
        ),
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


BUILTIN_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="get_account_balance",
        description=(
            "Return the debit/credit totals and net debit for one COA account, "
            "optionally as of a date (effective_date <= as_of)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "account_code": {"type": "string", "description": "COA code, e.g. '2050'"},
                "as_of": {"type": "string", "description": "YYYY-MM-DD (optional)"},
            },
            "required": ["account_code"],
        },
        fn=_get_account_balance,
    ),
    Tool(
        name="get_pnl",
        description="Profit & loss totals for a period (YYYY-MM).",
        input_schema={
            "type": "object",
            "properties": {"period": {"type": "string", "description": "YYYY-MM"}},
            "required": ["period"],
        },
        fn=_get_pnl,
    ),
    Tool(
        name="get_trial_balance",
        description=(
            "Sum of debits and credits across the GL, optionally restricted to "
            "a period. ``balanced=true`` when difference == 0."
        ),
        input_schema={
            "type": "object",
            "properties": {"period": {"type": "string", "description": "YYYY-MM (optional)"}},
            "required": [],
        },
        fn=_get_trial_balance,
    ),
    Tool(
        name="get_period_status",
        description="Current state of one accounting period (OPEN/IN_CLOSING/CLOSED/REOPENED).",
        input_schema={
            "type": "object",
            "properties": {"period": {"type": "string", "description": "YYYY-MM"}},
            "required": ["period"],
        },
        fn=_get_period_status,
    ),
    Tool(
        name="list_open_sanctions",
        description="Sanction requests still waiting on FA or CFO approval.",
        input_schema={"type": "object", "properties": {}, "required": []},
        fn=_list_open_sanctions,
    ),
    Tool(
        name="list_quarantine",
        description=(
            "Open rows in staging.data_quality_quarantine (unresolved validation failures)."
        ),
        input_schema={"type": "object", "properties": {}, "required": []},
        fn=_list_quarantine,
    ),
    Tool(
        name="list_recent_journals",
        description="Most recent posted journal entries (capped at 100).",
        input_schema={
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
            "required": [],
        },
        fn=_list_recent_journals,
    ),
)


def builtin_registry() -> dict[str, Tool]:
    """Return ``{tool_name: Tool}`` for the built-in read-only set."""
    return {t.name: t for t in BUILTIN_TOOLS}
