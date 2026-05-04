"""Property: post + reverse leaves trial balance unchanged."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.ledger.coa_loader import load_into_db
from src.ledger.posting import JournalEntryDraft, post_journal, reverse_journal
from src.ledger.subledger import build_default_registry
from tests.properties.conftest import topup_drafts, trial_balance_zero

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


def test_post_then_reverse_returns_to_baseline(
    db_session: Session,
    loaded_coa,
    some_students: list[int],
) -> None:
    registry = build_default_registry()

    @settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(draft=topup_drafts(some_students))
    def _one(draft: JournalEntryDraft) -> None:
        baseline = _wallet_total(db_session)
        posted = post_journal(db_session, draft, coa=loaded_coa, sub_ledgers=registry)
        assert _wallet_total(db_session) != baseline  # something happened
        reverse_journal(
            db_session,
            posted.je_id,
            narration="Property reversal of test posting",
            posted_by="hypothesis",
            coa=loaded_coa,
            sub_ledgers=registry,
        )
        assert _wallet_total(db_session) == baseline
        assert trial_balance_zero(db_session)

    _one()


def _wallet_total(session: Session):
    from decimal import Decimal

    val = session.execute(
        text("SELECT COALESCE(SUM(delta_aed), 0) FROM subledger.student_wallet_entries"),
    ).scalar_one()
    return Decimal(val)
