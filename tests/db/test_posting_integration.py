"""Integration: full post_journal + reverse_journal + sub-ledger application."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.exceptions import (
    PeriodClosedError,
    PeriodNotFoundError,
    ReversalError,
    UnbalancedJournalError,
    WalletNegativeError,
)
from src.ledger.coa import SubLedgerName
from src.ledger.coa_loader import load_into_db
from src.ledger.posting import (
    JournalEntryDraft,
    JournalLineDraft,
    post_journal,
    reverse_journal,
)
from src.ledger.subledger import build_default_registry

pytestmark = pytest.mark.integration


# ---- shared fixtures (function-scoped because db_session is) ---------------


@pytest.fixture
def loaded_coa(db_session: Session, coa_yaml_path: Path):
    load_into_db(db_session.connection(), yaml_path=coa_yaml_path)
    from src.ledger.coa import get_active_coa

    return get_active_coa()


@pytest.fixture
def registry():
    return build_default_registry()


@pytest.fixture
def open_period(db_session: Session) -> str:
    p = "2026-04"
    db_session.execute(
        text(
            "INSERT INTO master.periods (period, status, opened_at) "
            "VALUES (:p, 'OPEN', NOW()) "
            "ON CONFLICT (period) DO NOTHING",
        ),
        {"p": p},
    )
    return p


@pytest.fixture
def student(db_session: Session) -> int:
    return int(
        db_session.execute(
            text(
                "INSERT INTO master.students (display_id, name) "
                "VALUES ('S001', 'Test Student') RETURNING student_id",
            ),
        ).scalar_one(),
    )


@pytest.fixture
def tutor(db_session: Session) -> int:
    return int(
        db_session.execute(
            text(
                "INSERT INTO master.tutors (display_id, name, payment_currency) "
                "VALUES ('T01', 'Test Tutor', 'PKR') RETURNING tutor_id",
            ),
        ).scalar_one(),
    )


def _topup_draft(student_id: int, amount: str = "1000.00") -> JournalEntryDraft:
    return JournalEntryDraft(
        date=date(2026, 4, 5),
        narration="Wallet top-up integration test",
        source="manual:tester",
        source_kind="manual",
        posted_by="tester",
        lines=[
            JournalLineDraft(account_code="1010", debit_aed=Decimal(amount)),
            JournalLineDraft(
                account_code="2050",
                credit_aed=Decimal(amount),
                sub_ledger_keys={"student_id": student_id},
            ),
        ],
    )


# ---- happy paths -----------------------------------------------------------


def test_post_topup_succeeds(
    db_session: Session,
    loaded_coa,
    registry,
    open_period: str,
    student: int,
) -> None:
    posted = post_journal(
        db_session,
        _topup_draft(student),
        coa=loaded_coa,
        sub_ledgers=registry,
    )
    assert posted.je_id > 0
    assert posted.period == open_period
    assert posted.total_aed == Decimal("1000.00")
    # Sub-ledger row was written
    bal = registry.get(SubLedgerName.STUDENT_WALLET).balance(db_session, student)
    assert bal == Decimal("1000.00")
    # Audit row written
    assert (
        db_session.execute(
            text(
                "SELECT COUNT(*) FROM audit.audit_log WHERE action='POST_JOURNAL' AND success=true"
            ),
        ).scalar_one()
        == 1
    )


def test_audit_row_on_validation_failure(
    db_session: Session,
    loaded_coa,
    registry,
    open_period: str,
    student: int,
) -> None:
    bad = _topup_draft(student).model_copy(
        update={"narration": "short"},
    )
    with pytest.raises(Exception):
        post_journal(db_session, bad, coa=loaded_coa, sub_ledgers=registry)
    # After the exception, even if the test's outer transaction rolls back,
    # we should have an audit row inserted in this session before raise.
    n = db_session.execute(
        text("SELECT COUNT(*) FROM audit.audit_log WHERE success=false"),
    ).scalar_one()
    assert n == 1


# ---- validation rejections (full pipeline) ---------------------------------


def test_unbalanced_rejected(
    db_session: Session,
    loaded_coa,
    registry,
    open_period: str,
    student: int,
) -> None:
    bad = _topup_draft(student).model_copy(
        update={
            "lines": [
                JournalLineDraft(account_code="1010", debit_aed=Decimal("100.00")),
                JournalLineDraft(
                    account_code="2050",
                    credit_aed=Decimal("99.99"),
                    sub_ledger_keys={"student_id": student},
                ),
            ],
        },
    )
    with pytest.raises(UnbalancedJournalError):
        post_journal(db_session, bad, coa=loaded_coa, sub_ledgers=registry)


def test_period_not_found_rejected(
    db_session: Session,
    loaded_coa,
    registry,
    student: int,
) -> None:
    # No period seeded for 2027-01.
    bad = _topup_draft(student).model_copy(update={"date": date(2027, 1, 15)})
    with pytest.raises(PeriodNotFoundError):
        post_journal(db_session, bad, coa=loaded_coa, sub_ledgers=registry)


def test_period_closed_rejected(
    db_session: Session,
    loaded_coa,
    registry,
    open_period: str,
    student: int,
) -> None:
    db_session.execute(
        text("UPDATE master.periods SET status='CLOSED' WHERE period=:p"),
        {"p": open_period},
    )
    with pytest.raises(PeriodClosedError):
        post_journal(db_session, _topup_draft(student), coa=loaded_coa, sub_ledgers=registry)


# ---- wallet hard rule ------------------------------------------------------


def test_wallet_cannot_go_negative(
    db_session: Session,
    loaded_coa,
    registry,
    open_period: str,
    student: int,
) -> None:
    # Top up 100, then try to consume 200.
    post_journal(
        db_session,
        _topup_draft(student, amount="100.00"),
        coa=loaded_coa,
        sub_ledgers=registry,
    )
    consume = JournalEntryDraft(
        date=date(2026, 4, 6),
        narration="Wallet consume too much",
        source="system:revenue_agent",
        source_kind="system",
        posted_by="system",
        lines=[
            JournalLineDraft(
                account_code="2050",
                debit_aed=Decimal("200.00"),
                sub_ledger_keys={"student_id": student},
            ),
            JournalLineDraft(account_code="4010", credit_aed=Decimal("200.00")),
        ],
    )
    with pytest.raises(WalletNegativeError):
        post_journal(db_session, consume, coa=loaded_coa, sub_ledgers=registry)


# ---- reversal --------------------------------------------------------------


def test_reverse_journal_round_trip(
    db_session: Session,
    loaded_coa,
    registry,
    open_period: str,
    student: int,
) -> None:
    posted = post_journal(
        db_session,
        _topup_draft(student, amount="500.00"),
        coa=loaded_coa,
        sub_ledgers=registry,
    )
    sl = registry.get(SubLedgerName.STUDENT_WALLET)
    assert sl.balance(db_session, student) == Decimal("500.00")

    reversed_posted = reverse_journal(
        db_session,
        posted.je_id,
        narration="Reversal of test top-up",
        posted_by="tester",
        coa=loaded_coa,
        sub_ledgers=registry,
    )
    assert reversed_posted.je_id != posted.je_id
    # Wallet should be back to zero.
    assert sl.balance(db_session, student) == Decimal("0.00")
    # Original is now REVERSED.
    status = db_session.execute(
        text("SELECT status FROM ledger.journal_entries WHERE je_id=:id"),
        {"id": posted.je_id},
    ).scalar_one()
    assert status == "REVERSED"


def test_reverse_already_reversed_rejected(
    db_session: Session,
    loaded_coa,
    registry,
    open_period: str,
    student: int,
) -> None:
    posted = post_journal(db_session, _topup_draft(student), coa=loaded_coa, sub_ledgers=registry)
    reverse_journal(
        db_session,
        posted.je_id,
        narration="Reverse one",
        posted_by="tester",
        coa=loaded_coa,
        sub_ledgers=registry,
    )
    with pytest.raises(ReversalError):
        reverse_journal(
            db_session,
            posted.je_id,
            narration="Reverse twice (should fail)",
            posted_by="tester",
            coa=loaded_coa,
            sub_ledgers=registry,
        )


# ---- sub-ledger reconciliation --------------------------------------------


def test_wallet_reconciles_to_gl(
    db_session: Session,
    loaded_coa,
    registry,
    open_period: str,
    student: int,
) -> None:
    post_journal(
        db_session, _topup_draft(student, amount="100.00"), coa=loaded_coa, sub_ledgers=registry
    )
    post_journal(
        db_session, _topup_draft(student, amount="50.00"), coa=loaded_coa, sub_ledgers=registry
    )
    result = registry.get(SubLedgerName.STUDENT_WALLET).reconcile_to_gl(db_session)
    assert result.matches
    assert result.gl_balance == Decimal("150.00")
    assert result.sub_ledger_sum == Decimal("150.00")
