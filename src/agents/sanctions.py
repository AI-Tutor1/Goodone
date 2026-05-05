"""Sanctions Agent — request → FA → CFO → approved/rejected → spend.

State machine and JE rules per ``docs/accounting_rules.md`` §13–§14
(revised: 2060 / 9010 paired-account memo).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from src.core.config import get_settings
from src.core.money import aed
from src.email.provider import EmailMessageOut, get_email_provider
from src.ledger.posting import (
    JournalEntryDraft,
    JournalLineDraft,
    PostedJournal,
    post_journal,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


def submit(
    session: Session,
    *,
    department: str,
    title: str,
    amount_aed: Decimal,
    created_by: str,
) -> int:
    """Create a request in DRAFT → PENDING_FA."""
    sid = int(
        session.execute(
            text(
                "INSERT INTO sanctions.sanction_requests "
                "(department, title, amount_aed, status, created_by, created_at) "
                "VALUES (:d, :t, :a, 'PENDING_FA', :u, NOW()) RETURNING id",
            ),
            {"d": department, "t": title, "a": aed(amount_aed), "u": created_by},
        ).scalar_one(),
    )
    return sid


def fa_decide(session: Session, *, request_id: int, approve: bool, by: str) -> None:
    new_status = "PENDING_CFO" if approve else "REJECTED"
    session.execute(
        text(
            "UPDATE sanctions.sanction_requests SET status = :s WHERE id = :id",
        ),
        {"s": new_status, "id": request_id},
    )
    _audit(session, request_id, "FA_DECIDE", by, ok=approve)
    _notify_sanction(
        request_id=request_id,
        subject=f"Sanction #{request_id}: FA {'approved' if approve else 'rejected'} — {'awaiting CFO' if approve else 'closed'}",
        body=f"FA ({by}) {'approved' if approve else 'rejected'} sanction request #{request_id}.\n"
             + ("The request is now pending CFO review." if approve else "The request is now closed."),
        to_cfo=approve,
    )


def cfo_decide(
    session: Session,
    *,
    request_id: int,
    approve: bool,
    by: str,
    posting_date: date,
    coa,
    sub_ledgers,
) -> PostedJournal | None:
    """On approve, post the memo JE per §13. On reject, just close."""
    new_status = "APPROVED" if approve else "REJECTED"
    row = session.execute(
        text(
            "UPDATE sanctions.sanction_requests SET status = :s "
            "WHERE id = :id AND status = 'PENDING_CFO' "
            "RETURNING amount_aed",
        ),
        {"s": new_status, "id": request_id},
    ).one_or_none()
    if row is None:
        raise RuntimeError(f"sanction {request_id} is not in PENDING_CFO")
    _audit(session, request_id, "CFO_DECIDE", by, ok=approve)
    _notify_sanction(
        request_id=request_id,
        subject=f"Sanction #{request_id}: CFO {'approved' if approve else 'rejected'}",
        body=f"CFO ({by}) {'approved' if approve else 'rejected'} sanction request #{request_id}.",
        to_cfo=False,
    )
    if not approve:
        return None
    amount = aed(row.amount_aed)
    return post_journal(
        session,
        JournalEntryDraft(
            date=posting_date,
            narration=f"Sanction approved request={request_id}",
            source="system:sanctions_agent",
            source_kind="system",
            source_ref=f"SANCTION-{request_id}-APPROVE",
            source_version="0.1",
            posted_by=by,
            lines=[
                JournalLineDraft(
                    account_code="2060",
                    debit_aed=amount,
                    sub_ledger_keys={"sanction_request_id": request_id},
                ),
                JournalLineDraft(
                    account_code="9010",
                    credit_aed=amount,
                    sub_ledger_keys={"sanction_request_id": request_id},
                ),
            ],
        ),
        coa=coa,
        sub_ledgers=sub_ledgers,
    )


def post_spend(
    session: Session,
    *,
    request_id: int,
    expense_account: str,
    amount_aed: Decimal,
    posting_date: date,
    by: str,
    coa,
    sub_ledgers,
) -> tuple[PostedJournal, PostedJournal]:
    """Reverse the memo for *amount_aed* and post the real expense JE."""
    amount = aed(amount_aed)
    reversal = post_journal(
        session,
        JournalEntryDraft(
            date=posting_date,
            narration=f"Sanction memo reversal request={request_id}",
            source="system:sanctions_agent",
            source_kind="system",
            source_ref=f"SANCTION-{request_id}-SPEND-REV",
            source_version="0.1",
            posted_by=by,
            lines=[
                JournalLineDraft(
                    account_code="9010",
                    debit_aed=amount,
                    sub_ledger_keys={"sanction_request_id": request_id},
                ),
                JournalLineDraft(
                    account_code="2060",
                    credit_aed=amount,
                    sub_ledger_keys={"sanction_request_id": request_id},
                ),
            ],
        ),
        coa=coa,
        sub_ledgers=sub_ledgers,
    )
    expense = post_journal(
        session,
        JournalEntryDraft(
            date=posting_date,
            narration=(f"Sanction spend request={request_id} → {expense_account}"),
            source="system:sanctions_agent",
            source_kind="system",
            source_ref=f"SANCTION-{request_id}-SPEND-EXP",
            source_version="0.1",
            posted_by=by,
            lines=[
                JournalLineDraft(account_code=expense_account, debit_aed=amount),
                JournalLineDraft(account_code="1010", credit_aed=amount),
            ],
        ),
        coa=coa,
        sub_ledgers=sub_ledgers,
    )
    return reversal, expense


def _notify_sanction(
    *,
    request_id: int,
    subject: str,
    body: str,
    to_cfo: bool,
) -> None:
    """Fire-and-forget email; swallows errors so they never break the workflow."""
    try:
        s = get_settings()
        recipients: list[str] = []
        if to_cfo and getattr(s, "cfo_email", None):
            recipients.append(s.cfo_email)  # type: ignore[arg-type]
        elif not to_cfo and getattr(s, "fa_email", None):
            recipients.append(s.fa_email)  # type: ignore[arg-type]
        if not recipients:
            return
        get_email_provider().send(EmailMessageOut(to=recipients, subject=subject, body_text=body))
    except Exception:
        pass  # email failures must never abort a financial transaction


def _audit(
    session: Session,
    request_id: int,
    what: str,
    actor: str,
    *,
    ok: bool,
) -> None:
    session.execute(
        text(
            "INSERT INTO audit.audit_log "
            "(ts, actor, action, target_type, target_id, success) "
            "VALUES (NOW(), :actor, 'POST_JOURNAL', 'sanction_request', "
            "        :tid, :ok)",
        ),
        {"actor": actor, "tid": str(request_id), "ok": ok},
    )
    _ = what  # surfaced via target_id naming convention upstream
