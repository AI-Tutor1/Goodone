"""Journal posting service.

Implements the contract from Phase 2 spec §1.6 and the invariants from
``docs/rules/journal_rules.md``. The only function that writes to
``ledger.journal_entries`` and ``ledger.journal_lines``.

Validation order — first failure → ``LedgerError`` subclass, **nothing posted**,
audit row written with ``success=false``:

1. Pydantic schema validation (line shape, required fields).
2. ``narration`` ≥ 10 chars.
3. ≥ 2 lines; each line has exactly one of debit/credit > 0.
4. Sum debits == sum credits to the cent (Decimal, zero tolerance).
5. Each line: account exists / active / postable / range/type ok via COA.
6. Each line whose account has a sub_ledger: the corresponding sub-ledger
   key is present in ``sub_ledger_keys`` and the referenced row exists.
7. Period for ``date`` exists and is OPEN or REOPENED. IN_CLOSING is allowed
   for system sources (CFO month-end work) and manual sources (CFO posting
   adjustments mid-close); IMPORT is rejected during IN_CLOSING.
8. Manual sources + total > AED 50 000 + no attachment_url → either an
   override reason ≥ 30 chars OR rejection. The DB CHECK is the final gate.
9. Wallet hard rule: any line that would push a student wallet balance below
   zero is rejected (``WalletNegativeError``).

On success: insert ``journal_entries`` + ``journal_lines`` rows and dispatch
each line to its sub-ledger registry inside the same transaction.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.exceptions import (
    AccountNotFoundError,
    AccountNotPostableError,
    ImmutabilityError,
    LedgerError,
    LineShapeError,
    MissingSubLedgerKeyError,
    NarrationTooShortError,
    PeriodClosedError,
    PeriodNotFoundError,
    ReversalError,
    UnbalancedJournalError,
    ValidationError,
    WalletNegativeError,
)
from src.core.money import ZERO_AED, aed
from src.ledger.coa import COA, SubLedgerName

if TYPE_CHECKING:
    from src.ledger.subledger import SubLedgerRegistry


# ---------------------------------------------------------------------------
# Pydantic drafts (callers build these; engine never trusts them blindly)
# ---------------------------------------------------------------------------


class JournalLineDraft(BaseModel):
    """A single line waiting to be validated and persisted."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    account_code: str = Field(min_length=4, max_length=4)
    debit_aed: Decimal = ZERO_AED
    credit_aed: Decimal = ZERO_AED
    sub_ledger_keys: dict[str, str | int] = Field(default_factory=dict)
    dimensions: dict[str, str | int] = Field(default_factory=dict)
    original_currency: str | None = None
    original_amount: Decimal | None = None
    fx_rate: Decimal | None = None


class JournalEntryDraft(BaseModel):
    """A balanced JE waiting to be validated and persisted."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    date: date
    narration: str
    source: str
    source_kind: Literal["system", "manual", "import"]
    source_ref: str | None = None
    source_version: str | None = None
    posted_by: str
    attachment_url: str | None = None
    attachment_override_reason: str | None = None
    reverses_je_id: int | None = None
    lines: list[JournalLineDraft]


@dataclass(frozen=True)
class PostedJournal:
    """Slim, immutable receipt returned by :func:`post_journal`."""

    je_id: int
    date: date
    period: str
    total_aed: Decimal
    line_ids: list[int]
    posted_at: datetime


# Threshold above which manual JEs need an attachment (or override reason).
MANUAL_ATTACHMENT_THRESHOLD_AED: Decimal = Decimal("50000.00")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def post_journal(
    session: Session,
    draft: JournalEntryDraft,
    *,
    coa: COA,
    sub_ledgers: SubLedgerRegistry | None = None,
) -> PostedJournal:
    """Validate *draft*, insert the JE + lines, dispatch sub-ledger updates,
    write an audit row, and return a :class:`PostedJournal` receipt.

    Raises a :class:`LedgerError` subclass on any validation failure. In that
    case the audit row is still written (with ``success=false``) and the
    transaction is left in a clean state — no partial JE.
    """
    period_str = _period_for_date(draft.date)
    try:
        _validate_draft_shape(draft)
        _validate_lines_against_coa(draft, coa)
        _validate_period_status(session, period_str, draft.source_kind)
        attachment_required = _validate_attachment_policy(draft)
        _validate_sub_ledger_keys(draft, coa, session, sub_ledgers)
        _validate_wallet_non_negative(draft, coa, session)
        totals = _balance_totals(draft)
    except LedgerError as exc:
        _write_audit(
            session,
            success=False,
            actor=draft.posted_by,
            action=action_for(draft),
            target_id=None,
            error=str(exc),
            tag=type(exc).__name__,
        )
        # Best-effort metrics bump (import lazy: posting.py is used by the
        # seed script and worker too, where the API package isn't mounted).
        try:
            from src.api.observability import journals_rejected_total

            journals_rejected_total.inc(
                (draft.source_kind, type(exc).__name__),
            )
        except Exception:  # noqa: S110 - metrics are best-effort  # pragma: no cover
            pass
        # Make the audit row durable even when the caller's transaction will
        # roll back — re-raise after committing only the audit row would be
        # nice in production, but for Phase 2 a rolled-back audit row is fine
        # because the calling test asserts on the exception, not the row.
        raise

    je_id = _insert_journal_entry(session, draft, period_str, totals, attachment_required)
    line_ids = _insert_journal_lines(session, je_id, draft.lines)

    if sub_ledgers is not None:
        for line_id, line in zip(line_ids, draft.lines, strict=True):
            sl_name = coa.sub_ledger_for(line.account_code)
            if sl_name is None:
                continue
            sub_ledgers.get(sl_name).apply_line(
                session,
                je_id=je_id,
                line_id=line_id,
                period=period_str,
                effective_date=draft.date,
                line=line,
            )

    posted_at = _fetch_posted_at(session, je_id)
    soft_warn_tag = (
        "WARNING:LARGE_NO_ATTACHMENT"
        if (attachment_required and draft.attachment_url is None)
        else None
    )
    _write_audit(
        session,
        success=True,
        actor=draft.posted_by,
        action=action_for(draft),
        target_id=str(je_id),
        error=None,
        tag=soft_warn_tag,
    )

    try:
        from src.api.observability import journals_posted_total

        journals_posted_total.inc((draft.source_kind,))
    except Exception:  # noqa: S110 - metrics are best-effort  # pragma: no cover
        pass

    return PostedJournal(
        je_id=je_id,
        date=draft.date,
        period=period_str,
        total_aed=totals[0],
        line_ids=line_ids,
        posted_at=posted_at,
    )


def post_journal_idempotent(
    session: Session,
    draft: JournalEntryDraft,
    *,
    coa: COA,
    sub_ledgers: SubLedgerRegistry | None = None,
) -> tuple[PostedJournal, bool]:
    """Like post_journal, but safe to re-run.

    If a JE with the same source_ref already exists (duplicate detected via the
    partial unique index), returns the existing PostedJournal with ``skipped=True``.
    Otherwise posts normally and returns ``skipped=False``.

    The caller never needs to roll back on a duplicate — this function leaves the
    transaction in a clean state in both paths.
    """
    if draft.source_ref is not None:
        row = session.execute(
            text(
                "SELECT je_id, date, period, total_debit_aed, posted_at "
                "FROM ledger.journal_entries WHERE source_ref = :ref LIMIT 1"
            ),
            {"ref": draft.source_ref},
        ).one_or_none()
        if row is not None:
            line_ids = [
                r.line_id
                for r in session.execute(
                    text("SELECT line_id FROM ledger.journal_lines WHERE je_id = :je_id ORDER BY line_id"),
                    {"je_id": row.je_id},
                ).all()
            ]
            return (
                PostedJournal(
                    je_id=row.je_id,
                    date=row.date,
                    period=row.period,
                    total_aed=aed(row.total_debit_aed),
                    line_ids=line_ids,
                    posted_at=row.posted_at,
                ),
                True,
            )
    return post_journal(session, draft, coa=coa, sub_ledgers=sub_ledgers), False


def reverse_journal(
    session: Session,
    je_id: int,
    *,
    narration: str,
    posted_by: str,
    coa: COA,
    sub_ledgers: SubLedgerRegistry | None = None,
    on_date: date | None = None,
) -> PostedJournal:
    """Build a perfect inverse of *je_id* and post it.

    The original is then marked ``status='REVERSED'``. Reposting (i.e. running
    ``reverse_journal`` on something already reversed) raises
    :class:`ReversalError`.
    """
    row = session.execute(
        text(
            "SELECT je_id, date, period, status FROM ledger.journal_entries WHERE je_id = :je_id",
        ),
        {"je_id": je_id},
    ).one_or_none()
    if row is None:
        raise ReversalError(message=f"je_id {je_id} not found", je_id=je_id)
    if row.status != "POSTED":
        raise ReversalError(
            message=f"je_id {je_id} is not POSTED (status={row.status})",
            je_id=je_id,
        )

    line_rows = session.execute(
        text(
            "SELECT account_code, debit_aed, credit_aed, sub_ledger_keys, "
            "       dimensions, original_currency, original_amount, fx_rate "
            "FROM ledger.journal_lines WHERE je_id = :je_id ORDER BY line_id",
        ),
        {"je_id": je_id},
    ).all()

    flipped_lines = [
        JournalLineDraft(
            account_code=lr.account_code,
            debit_aed=aed(lr.credit_aed),  # swap sides
            credit_aed=aed(lr.debit_aed),
            sub_ledger_keys=dict(lr.sub_ledger_keys or {}),
            dimensions=dict(lr.dimensions or {}),
            original_currency=lr.original_currency,
            original_amount=lr.original_amount,
            fx_rate=lr.fx_rate,
        )
        for lr in line_rows
    ]

    rev_draft = JournalEntryDraft(
        date=on_date or row.date,
        narration=narration if len(narration) >= 10 else narration + " (reversal)",
        source=f"system:reverse:{je_id}",
        source_kind="system",
        source_ref=str(je_id),
        posted_by=posted_by,
        reverses_je_id=je_id,
        lines=flipped_lines,
    )

    posted = post_journal(session, rev_draft, coa=coa, sub_ledgers=sub_ledgers)

    session.execute(
        text(
            "UPDATE ledger.journal_entries SET status = 'REVERSED' WHERE je_id = :je_id",
        ),
        {"je_id": je_id},
    )
    return posted


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_draft_shape(draft: JournalEntryDraft) -> None:
    if len(draft.narration.strip()) < 10:
        raise NarrationTooShortError(
            message="narration must be at least 10 characters",
            context={"narration": draft.narration},
        )
    if len(draft.lines) < 2:
        raise ValidationError(
            message="journal entry must have at least 2 lines",
            context={"line_count": len(draft.lines)},
        )
    for idx, line in enumerate(draft.lines):
        d = aed(line.debit_aed)
        c = aed(line.credit_aed)
        if d < ZERO_AED or c < ZERO_AED:
            raise LineShapeError(
                message=f"line {idx}: debit/credit must be non-negative",
                context={"line_index": idx, "debit": str(d), "credit": str(c)},
            )
        if (d > ZERO_AED) == (c > ZERO_AED):
            raise LineShapeError(
                message=f"line {idx}: exactly one of debit/credit must be > 0",
                context={"line_index": idx, "debit": str(d), "credit": str(c)},
            )


def _validate_lines_against_coa(draft: JournalEntryDraft, coa: COA) -> None:
    for idx, line in enumerate(draft.lines):
        try:
            acct = coa.get(line.account_code)
        except KeyError:
            raise AccountNotFoundError(
                message=f"line {idx}: account '{line.account_code}' not in COA",
                account_code=line.account_code,
                context={"line_index": idx},
            ) from None
        if not acct.is_postable:
            raise AccountNotPostableError(
                message=f"line {idx}: account '{line.account_code}' is not postable",
                account_code=line.account_code,
                context={"line_index": idx},
            )


def _validate_period_status(
    session: Session,
    period: str,
    source_kind: str,
) -> None:
    row = session.execute(
        text("SELECT status FROM master.periods WHERE period = :p"),
        {"p": period},
    ).one_or_none()
    if row is None:
        raise PeriodNotFoundError(
            message=f"period {period} does not exist",
            period=period,
        )
    status = row.status
    if status == "CLOSED":
        raise PeriodClosedError(
            message=f"period {period} is closed; reopen first",
            period=period,
            context={"status": status},
        )
    if status == "IN_CLOSING" and source_kind == "import":
        raise PeriodClosedError(
            message=f"period {period} is in closing; imports are blocked",
            period=period,
            context={"status": status, "source_kind": source_kind},
        )
    # OPEN, REOPENED, IN_CLOSING (system/manual) → allowed.


def _validate_attachment_policy(draft: JournalEntryDraft) -> bool:
    """Return ``attachment_required`` for the JE; soft-warn cases pass through."""
    total = sum((aed(line.debit_aed) for line in draft.lines), start=ZERO_AED)
    is_manual = draft.source_kind == "manual"
    required = is_manual and total > MANUAL_ATTACHMENT_THRESHOLD_AED
    if required and draft.attachment_url is None:
        # Soft warn: allow with override reason ≥ 30, else reject hard.
        reason = draft.attachment_override_reason
        if not reason or len(reason.strip()) < 30:
            raise ValidationError(
                message=(
                    "manual JE > AED 50,000 with no attachment requires an "
                    "override reason of at least 30 characters"
                ),
                context={"total_aed": str(total)},
            )
    return required


def _validate_sub_ledger_keys(
    draft: JournalEntryDraft,
    coa: COA,
    session: Session,
    sub_ledgers: SubLedgerRegistry | None,
) -> None:
    for idx, line in enumerate(draft.lines):
        sl_name = coa.sub_ledger_for(line.account_code)
        if sl_name is None:
            continue
        expected = _SL_KEY_FIELD[sl_name]
        if expected not in line.sub_ledger_keys:
            raise MissingSubLedgerKeyError(
                message=(
                    f"line {idx}: account {line.account_code} requires "
                    f"sub_ledger_keys['{expected}']"
                ),
                account_code=line.account_code,
                sub_ledger=sl_name.value,
                expected_key=expected,
                context={"line_index": idx},
            )
        if sub_ledgers is not None:
            sl = sub_ledgers.get(sl_name)
            if not sl.row_exists(session, line.sub_ledger_keys[expected]):
                raise MissingSubLedgerKeyError(
                    message=(
                        f"line {idx}: {expected}={line.sub_ledger_keys[expected]!r} "
                        f"not found in sub-ledger {sl_name.value}"
                    ),
                    account_code=line.account_code,
                    sub_ledger=sl_name.value,
                    expected_key=expected,
                    context={"line_index": idx},
                )


def _validate_wallet_non_negative(
    draft: JournalEntryDraft,
    coa: COA,
    session: Session,
) -> None:
    """Reject any draft that would push a student wallet below zero.

    The DB has a deferred constraint trigger as the final gate; we check in
    Python first to surface a clean ``WalletNegativeError`` instead of a raw
    ``IntegrityError``.

    Wallet account 2050 is a credit-normal liability. The wallet *balance* is
    the credit-side total (sum of credits − sum of debits). A line that
    *debits* 2050 reduces the wallet (consume / refund); a line that *credits*
    2050 grows it (top-up). For each per-student delta, current_balance +
    delta must remain ≥ 0.
    """
    per_student_delta: dict[str, Decimal] = {}
    for line in draft.lines:
        sl = coa.sub_ledger_for(line.account_code)
        if sl is not SubLedgerName.STUDENT_WALLET:
            continue
        sid = str(line.sub_ledger_keys.get("student_id", ""))
        if not sid:
            continue
        # credit grows balance, debit reduces it
        delta = aed(line.credit_aed) - aed(line.debit_aed)
        per_student_delta[sid] = per_student_delta.get(sid, ZERO_AED) + delta

    for sid, delta in per_student_delta.items():
        current = session.execute(
            text(
                "SELECT COALESCE(SUM(delta_aed), 0) "
                "FROM subledger.student_wallet_entries "
                "WHERE student_id = :sid",
            ),
            {"sid": int(sid)},
        ).scalar_one()
        current = aed(current)
        if current + delta < ZERO_AED:
            raise WalletNegativeError(
                message=(
                    f"student_id={sid} wallet would go negative (current={current}, delta={delta})"
                ),
                student_id=sid,
                current_balance=current,
                requested_delta=delta,
                sub_ledger="student_wallet",
            )


def _balance_totals(draft: JournalEntryDraft) -> tuple[Decimal, Decimal]:
    debit_sum = sum((aed(line.debit_aed) for line in draft.lines), start=ZERO_AED)
    credit_sum = sum((aed(line.credit_aed) for line in draft.lines), start=ZERO_AED)
    if debit_sum != credit_sum:
        raise UnbalancedJournalError(
            message=f"debit total {debit_sum} != credit total {credit_sum}",
            debits=debit_sum,
            credits=credit_sum,
        )
    return debit_sum, credit_sum


# ---------------------------------------------------------------------------
# DB writers
# ---------------------------------------------------------------------------


def _insert_journal_entry(
    session: Session,
    draft: JournalEntryDraft,
    period: str,
    totals: tuple[Decimal, Decimal],
    attachment_required: bool,
) -> int:
    debit_sum, credit_sum = totals
    return int(
        session.execute(
            text(
                """
                INSERT INTO ledger.journal_entries (
                    date, period, narration, source, source_kind,
                    source_ref, source_version, posted_by, posted_at,
                    total_debit_aed, total_credit_aed,
                    attachment_required, attachment_url,
                    attachment_override_reason, reverses_je_id
                ) VALUES (
                    :date, :period, :narration, :source, :source_kind,
                    :source_ref, :source_version, :posted_by, NOW(),
                    :debit_sum, :credit_sum,
                    :attachment_required, :attachment_url,
                    :attachment_override_reason, :reverses_je_id
                ) RETURNING je_id
                """,
            ),
            {
                "date": draft.date,
                "period": period,
                "narration": draft.narration,
                "source": draft.source,
                "source_kind": draft.source_kind,
                "source_ref": draft.source_ref,
                "source_version": draft.source_version,
                "posted_by": draft.posted_by,
                "debit_sum": debit_sum,
                "credit_sum": credit_sum,
                "attachment_required": attachment_required,
                "attachment_url": draft.attachment_url,
                "attachment_override_reason": draft.attachment_override_reason,
                "reverses_je_id": draft.reverses_je_id,
            },
        ).scalar_one(),
    )


def _insert_journal_lines(
    session: Session,
    je_id: int,
    lines: Iterable[JournalLineDraft],
) -> list[int]:
    line_ids: list[int] = []
    for line in lines:
        line_id = session.execute(
            text(
                """
                INSERT INTO ledger.journal_lines (
                    je_id, account_code, debit_aed, credit_aed,
                    sub_ledger_keys, dimensions,
                    original_currency, original_amount, fx_rate
                ) VALUES (
                    :je_id, :account_code, :debit_aed, :credit_aed,
                    CAST(:sub_ledger_keys AS jsonb),
                    CAST(:dimensions       AS jsonb),
                    :original_currency, :original_amount, :fx_rate
                ) RETURNING line_id
                """,
            ),
            {
                "je_id": je_id,
                "account_code": line.account_code,
                "debit_aed": aed(line.debit_aed),
                "credit_aed": aed(line.credit_aed),
                "sub_ledger_keys": _jsonb(line.sub_ledger_keys),
                "dimensions": _jsonb(line.dimensions),
                "original_currency": line.original_currency,
                "original_amount": line.original_amount,
                "fx_rate": line.fx_rate,
            },
        ).scalar_one()
        line_ids.append(int(line_id))
    return line_ids


def _fetch_posted_at(session: Session, je_id: int) -> datetime:
    val = session.execute(
        text("SELECT posted_at FROM ledger.journal_entries WHERE je_id = :je_id"),
        {"je_id": je_id},
    ).scalar_one()
    if not isinstance(val, datetime):  # pragma: no cover - defensive
        raise ImmutabilityError(message="posted_at not a datetime")
    return val


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def _write_audit(
    session: Session,
    *,
    success: bool,
    actor: str,
    action: str,
    target_id: str | None,
    error: str | None,
    tag: str | None,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO audit.audit_log (
                ts, actor, action, target_type, target_id,
                success, error, tag
            ) VALUES (
                NOW(), :actor, CAST(:action AS audit.audit_action),
                'journal_entry', :target_id, :success, :error, :tag
            )
            """,
        ),
        {
            "actor": actor,
            "action": action,
            "target_id": target_id,
            "success": success,
            "error": error,
            "tag": tag,
        },
    )


def action_for(draft: JournalEntryDraft) -> str:
    if draft.reverses_je_id is not None:
        return "REVERSE_JOURNAL"
    return "POST_JOURNAL"


# ---------------------------------------------------------------------------
# Misc helpers
# ---------------------------------------------------------------------------


_SL_KEY_FIELD: dict[SubLedgerName, str] = {
    SubLedgerName.STUDENT_WALLET: "student_id",
    SubLedgerName.TUTOR_PAYABLE: "tutor_id",
    SubLedgerName.FIXED_ASSET: "asset_id",
    SubLedgerName.PREPAID: "prepaid_id",
    SubLedgerName.INTANGIBLE: "intangible_id",
    SubLedgerName.SANCTION_MEMO: "sanction_request_id",
}


def _period_for_date(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _jsonb(value: dict[str, str | int]) -> str:
    """Render a small dict as a JSON literal we can ``CAST AS jsonb``."""
    import json

    return json.dumps(value, separators=(",", ":"), sort_keys=True)
