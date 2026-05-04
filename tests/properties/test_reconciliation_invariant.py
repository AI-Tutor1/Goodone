"""Property: after any random sequence of valid wallet postings,
control account 2050 reconciles to the wallet sub-ledger sum."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.ledger.coa import SubLedgerName
from src.ledger.coa_loader import load_into_db
from src.ledger.posting import JournalEntryDraft, post_journal
from src.ledger.subledger import build_default_registry
from tests.properties.conftest import topup_drafts

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


def test_wallet_reconciles_after_random_topups(
    db_session: Session,
    loaded_coa,
    some_students: list[int],
) -> None:
    registry = build_default_registry()
    sl = registry.get(SubLedgerName.STUDENT_WALLET)

    @settings(
        max_examples=20,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(draft=topup_drafts(some_students))
    def _one(draft: JournalEntryDraft) -> None:
        post_journal(db_session, draft, coa=loaded_coa, sub_ledgers=registry)
        result = sl.reconcile_to_gl(db_session)
        assert result.matches, (
            f"reconcile failed: gl={result.gl_balance} sub={result.sub_ledger_sum} "
            f"diff={result.diff}"
        )

    _one()
