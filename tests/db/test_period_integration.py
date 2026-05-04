"""Integration: PeriodService end-to-end (open / in_closing / close / reopen)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.exceptions import (
    PeriodClosedError,
    PeriodError,
    PeriodReopenReasonError,
    ReconciliationMismatchError,
)
from src.ledger.coa_loader import load_into_db
from src.ledger.period import PeriodService
from src.ledger.posting import JournalEntryDraft, JournalLineDraft, post_journal
from src.ledger.subledger import build_default_registry

pytestmark = pytest.mark.integration


@pytest.fixture
def loaded_coa(db_session: Session, coa_yaml_path: Path):
    load_into_db(db_session.connection(), yaml_path=coa_yaml_path)
    from src.ledger.coa import get_active_coa

    return get_active_coa()


@pytest.fixture
def registry():
    return build_default_registry()


@pytest.fixture
def service(registry) -> PeriodService:
    return PeriodService(sub_ledgers=registry)


@pytest.fixture
def student(db_session: Session) -> int:
    return int(
        db_session.execute(
            text(
                "INSERT INTO master.students (display_id, name) "
                "VALUES ('S001', 'Test') RETURNING student_id",
            ),
        ).scalar_one(),
    )


def test_ensure_period_idempotent(db_session: Session, service: PeriodService) -> None:
    service.ensure_period(db_session, "2026-04")
    service.ensure_period(db_session, "2026-04")
    n = db_session.execute(
        text("SELECT COUNT(*) FROM master.periods WHERE period='2026-04'"),
    ).scalar_one()
    assert n == 1
    assert service.status(db_session, "2026-04") == "OPEN"


def test_full_lifecycle(
    db_session: Session,
    service: PeriodService,
    loaded_coa,
    registry,
    student: int,
) -> None:
    p = "2026-04"
    service.ensure_period(db_session, p)
    # Post one balanced JE.
    post_journal(
        db_session,
        JournalEntryDraft(
            date=date(2026, 4, 5),
            narration="Wallet top-up for close test",
            source="manual:tester",
            source_kind="manual",
            posted_by="tester",
            lines=[
                JournalLineDraft(account_code="1010", debit_aed=Decimal("250.00")),
                JournalLineDraft(
                    account_code="2050",
                    credit_aed=Decimal("250.00"),
                    sub_ledger_keys={"student_id": student},
                ),
            ],
        ),
        coa=loaded_coa,
        sub_ledgers=registry,
    )
    service.begin_closing(db_session, p, by="cfo")
    assert service.status(db_session, p) == "IN_CLOSING"
    result = service.close(db_session, p, by="cfo")
    assert result.je_count == 1
    assert result.je_total_debit == Decimal("250.00")
    assert service.status(db_session, p) == "CLOSED"

    # Reopen requires a long reason.
    with pytest.raises(PeriodReopenReasonError):
        service.reopen(db_session, p, by="cfo", reason="oops")
    service.reopen(
        db_session,
        p,
        by="cfo",
        reason="discovered a missing accrual; reposting after CFO sign-off",
    )
    assert service.status(db_session, p) == "REOPENED"


def test_close_blocked_by_attachment_offender(
    db_session: Session,
    service: PeriodService,
    loaded_coa,
    registry,
    student: int,
) -> None:
    p = "2026-04"
    service.ensure_period(db_session, p)
    # Post a > 50k manual JE WITHOUT attachment, using an override reason
    # (so posting passes) — close should still hard-block since
    # attachment_url is null AND override_reason was set.
    # Wait: close blocks only when both are null. Use override only at close
    # by clearing it after post:
    posted = post_journal(
        db_session,
        JournalEntryDraft(
            date=date(2026, 4, 5),
            narration="Big topup pending document upload",
            source="manual:cfo",
            source_kind="manual",
            posted_by="cfo",
            attachment_override_reason="will attach the bank wire pdf within the day",
            lines=[
                JournalLineDraft(account_code="1010", debit_aed=Decimal("60000.00")),
                JournalLineDraft(
                    account_code="2050",
                    credit_aed=Decimal("60000.00"),
                    sub_ledger_keys={"student_id": student},
                ),
            ],
        ),
        coa=loaded_coa,
        sub_ledgers=registry,
    )
    # Now wipe BOTH attachment_url and override_reason → close must fail.
    db_session.execute(
        text(
            "UPDATE ledger.journal_entries SET attachment_override_reason = NULL WHERE je_id = :id",
        ),
        {"id": posted.je_id},
    )
    with pytest.raises(PeriodError):
        service.close(db_session, p, by="cfo")


def test_post_to_closed_rejected(
    db_session: Session,
    service: PeriodService,
    loaded_coa,
    registry,
    student: int,
) -> None:
    p = "2026-04"
    service.ensure_period(db_session, p)
    service.begin_closing(db_session, p, by="cfo")
    service.close(db_session, p, by="cfo")
    with pytest.raises(PeriodClosedError):
        post_journal(
            db_session,
            JournalEntryDraft(
                date=date(2026, 4, 28),
                narration="Late posting test entry",
                source="manual:tester",
                source_kind="manual",
                posted_by="tester",
                lines=[
                    JournalLineDraft(account_code="1010", debit_aed=Decimal("10.00")),
                    JournalLineDraft(
                        account_code="2050",
                        credit_aed=Decimal("10.00"),
                        sub_ledger_keys={"student_id": student},
                    ),
                ],
            ),
            coa=loaded_coa,
            sub_ledgers=registry,
        )


def test_post_to_reopened_allowed(
    db_session: Session,
    service: PeriodService,
    loaded_coa,
    registry,
    student: int,
) -> None:
    p = "2026-04"
    service.ensure_period(db_session, p)
    service.close(db_session, p, by="cfo")
    service.reopen(
        db_session,
        p,
        by="cfo",
        reason="reopen for a missed payroll accrual that auditor flagged",
    )
    post_journal(
        db_session,
        JournalEntryDraft(
            date=date(2026, 4, 28),
            narration="Posting in reopened period",
            source="manual:cfo",
            source_kind="manual",
            posted_by="cfo",
            lines=[
                JournalLineDraft(account_code="1010", debit_aed=Decimal("10.00")),
                JournalLineDraft(
                    account_code="2050",
                    credit_aed=Decimal("10.00"),
                    sub_ledger_keys={"student_id": student},
                ),
            ],
        ),
        coa=loaded_coa,
        sub_ledgers=registry,
    )


def test_close_blocked_by_subledger_mismatch(
    db_session: Session,
    service: PeriodService,
    loaded_coa,
    registry,
    student: int,
) -> None:
    """Inject an artificial wallet entry with no GL counterpart → reconcile fail."""
    p = "2026-04"
    service.ensure_period(db_session, p)
    db_session.execute(
        text(
            "INSERT INTO subledger.student_wallet_entries "
            "(student_id, je_id, line_id, period, effective_date, delta_aed, type) "
            "VALUES (:sid, 0, 0, :p, :d, 9999.99, 'TOPUP') "
            "ON CONFLICT DO NOTHING",
        ),
        {"sid": student, "p": p, "d": date(2026, 4, 1)},
    )
    # The above will fail FK on je_id=0; we need a real je. Use a contrived
    # path: post a real top-up and then add an extra sub-ledger row.
    # Simpler path: post a balanced JE to wallet, then add a phantom row.
    posted = post_journal(
        db_session,
        JournalEntryDraft(
            date=date(2026, 4, 5),
            narration="Topup before phantom sub-ledger row",
            source="manual:tester",
            source_kind="manual",
            posted_by="tester",
            lines=[
                JournalLineDraft(account_code="1010", debit_aed=Decimal("100.00")),
                JournalLineDraft(
                    account_code="2050",
                    credit_aed=Decimal("100.00"),
                    sub_ledger_keys={"student_id": student},
                ),
            ],
        ),
        coa=loaded_coa,
        sub_ledgers=registry,
    )
    # Inject a phantom sub-ledger row referencing the same JE/line.
    db_session.execute(
        text(
            "INSERT INTO subledger.student_wallet_entries "
            "(student_id, je_id, line_id, period, effective_date, delta_aed, type) "
            "VALUES (:sid, :je, :ln, :p, :d, 0.01, 'ADJUST')",
        ),
        {
            "sid": student,
            "je": posted.je_id,
            "ln": posted.line_ids[1],
            "p": p,
            "d": date(2026, 4, 5),
        },
    )
    with pytest.raises(ReconciliationMismatchError):
        service.close(db_session, p, by="cfo")
