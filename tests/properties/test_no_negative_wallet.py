"""Property: at no point in any random sequence does a wallet go negative.

We seed each student with a known opening balance, then any consumption
above that balance must be hard-rejected; any consumption ≤ balance must
succeed and leave the post-consume balance ≥ 0.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.core.exceptions import WalletNegativeError
from src.ledger.coa import SubLedgerName
from src.ledger.coa_loader import load_into_db
from src.ledger.posting import JournalEntryDraft, JournalLineDraft, post_journal
from src.ledger.subledger import build_default_registry
from tests.properties.conftest import consume_drafts

pytestmark = pytest.mark.integration


@pytest.fixture
def loaded_coa(db_session: Session, coa_yaml_path: Path):
    load_into_db(db_session.connection(), yaml_path=coa_yaml_path)
    db_session.execute(
        text(
            "INSERT INTO master.periods (period, status, opened_at) "
            "VALUES ('2026-04', 'OPEN', NOW()) ON CONFLICT DO NOTHING",
        ),
    )
    from src.ledger.coa import get_active_coa

    return get_active_coa()


def _seed_topup(student_id: int, amount: str = "500.00") -> JournalEntryDraft:
    return JournalEntryDraft(
        date=date(2026, 4, 1),
        narration="Property test seed top-up",
        source="manual:hypothesis",
        source_kind="manual",
        posted_by="hypothesis",
        lines=[
            JournalLineDraft(account_code="1010", debit_aed=Decimal(amount)),
            JournalLineDraft(
                account_code="2050",
                credit_aed=Decimal(amount),
                sub_ledger_keys={"student_id": student_id},
            ),
        ],
    )


def test_consume_above_balance_always_rejected(
    db_session: Session,
    loaded_coa,
    some_students: list[int],
) -> None:
    """Whatever the random consume amount, if it exceeds current balance the
    engine raises WalletNegativeError; otherwise the wallet never goes < 0."""
    registry = build_default_registry()
    sl = registry.get(SubLedgerName.STUDENT_WALLET)

    for sid in some_students:
        post_journal(
            db_session,
            _seed_topup(sid),
            coa=loaded_coa,
            sub_ledgers=registry,
        )

    @settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(consume=consume_drafts(some_students, max_amount=Decimal("1000.00")))
    def _one(consume: JournalEntryDraft) -> None:
        consume_line = next(line for line in consume.lines if line.account_code == "2050")
        student_id = int(consume_line.sub_ledger_keys["student_id"])
        amount = Decimal(consume_line.debit_aed)
        current = sl.balance(db_session, student_id)
        if amount > current:
            with pytest.raises(WalletNegativeError):
                post_journal(db_session, consume, coa=loaded_coa, sub_ledgers=registry)
        else:
            post_journal(db_session, consume, coa=loaded_coa, sub_ledgers=registry)
            assert sl.balance(db_session, student_id) >= Decimal("0.00")

    _one()
