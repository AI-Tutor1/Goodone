"""Integration: COA loader writes the YAML into master.chart_of_accounts and
is idempotent on re-run.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.ledger.coa import COA, get_active_coa, reset_active_coa_for_tests
from src.ledger.coa_loader import load_into_db

pytestmark = pytest.mark.integration


def test_loader_inserts_every_account(db_session: Session, coa_yaml_path: Path) -> None:
    reset_active_coa_for_tests()
    written = load_into_db(db_session.connection(), yaml_path=coa_yaml_path)
    coa = COA.load_from_yaml(coa_yaml_path)
    assert written == len(coa.accounts)
    db_count = db_session.execute(
        text("SELECT COUNT(*) FROM master.chart_of_accounts"),
    ).scalar_one()
    assert db_count == len(coa.accounts)


def test_loader_idempotent(db_session: Session, coa_yaml_path: Path) -> None:
    reset_active_coa_for_tests()
    load_into_db(db_session.connection(), yaml_path=coa_yaml_path)
    db_count_before = db_session.execute(
        text("SELECT COUNT(*) FROM master.chart_of_accounts"),
    ).scalar_one()
    load_into_db(db_session.connection(), yaml_path=coa_yaml_path)  # second run
    db_count_after = db_session.execute(
        text("SELECT COUNT(*) FROM master.chart_of_accounts"),
    ).scalar_one()
    assert db_count_before == db_count_after


def test_loader_sets_active_coa_singleton(db_session: Session, coa_yaml_path: Path) -> None:
    reset_active_coa_for_tests()
    load_into_db(db_session.connection(), yaml_path=coa_yaml_path)
    active = get_active_coa()
    assert active.get("9010").is_memo is True


def test_memo_account_round_trips_to_db(db_session: Session, coa_yaml_path: Path) -> None:
    reset_active_coa_for_tests()
    load_into_db(db_session.connection(), yaml_path=coa_yaml_path)
    row = db_session.execute(
        text(
            "SELECT code, type::text, statement::text, is_memo, subtype "
            "FROM master.chart_of_accounts WHERE code = '9010'",
        ),
    ).one()
    assert row.code == "9010"
    assert row.type == "memo"
    assert row.statement == "MEMO"
    assert row.is_memo is True
    assert row.subtype == "memo"
