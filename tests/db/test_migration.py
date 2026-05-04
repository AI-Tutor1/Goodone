"""Integration: Alembic 0001_initial applies and CHECK constraints bite.

Marked ``integration`` so unit-test runs (``make test``) don't require Docker.
Run with ``make test-int`` or ``pytest -m integration``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


# ---- Schema / table presence ----------------------------------------------


def test_seven_schemas_present(db_session: Session) -> None:
    rows = (
        db_session.execute(
            text(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name IN ('master','ledger','subledger',"
                "'assets','sanctions','audit','staging') "
                "ORDER BY schema_name",
            ),
        )
        .scalars()
        .all()
    )
    assert set(rows) == {
        "master",
        "ledger",
        "subledger",
        "assets",
        "sanctions",
        "audit",
        "staging",
    }


@pytest.mark.parametrize(
    ("schema", "table"),
    [
        ("master", "chart_of_accounts"),
        ("master", "periods"),
        ("master", "students"),
        ("master", "tutors"),
        ("master", "enrollments"),
        ("master", "tutor_hour_rates"),
        ("master", "student_hour_rates"),
        ("master", "fx_rates"),
        ("ledger", "journal_entries"),
        ("ledger", "journal_lines"),
        ("subledger", "student_wallet_entries"),
        ("subledger", "tutor_payable_entries"),
        ("subledger", "sanction_memo_entries"),
        ("assets", "fixed_assets"),
        ("assets", "fixed_asset_depreciation_entries"),
        ("assets", "prepaids"),
        ("assets", "prepaid_amortization_entries"),
        ("assets", "intangibles"),
        ("assets", "intangible_entries"),
        ("sanctions", "sanction_requests"),
        ("audit", "audit_log"),
        ("audit", "period_close_log"),
        ("staging", "data_quality_quarantine"),
    ],
)
def test_table_exists(db_session: Session, schema: str, table: str) -> None:
    exists = db_session.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :s AND table_name = :t)",
        ),
        {"s": schema, "t": table},
    ).scalar()
    assert exists, f"missing {schema}.{table}"


# ---- CHECK constraints actually reject ------------------------------------


def _seed_period(db_session: Session, period: str = "2026-04") -> None:
    db_session.execute(
        text(
            "INSERT INTO master.periods (period, status, opened_at) "
            "VALUES (:p, 'OPEN', NOW()) "
            "ON CONFLICT (period) DO NOTHING",
        ),
        {"p": period},
    )


def test_unbalanced_journal_rejected(db_session: Session) -> None:
    _seed_period(db_session)
    with pytest.raises(IntegrityError) as exc:
        db_session.execute(
            text(
                "INSERT INTO ledger.journal_entries "
                "(date, period, narration, source, source_kind, posted_by, "
                " total_debit_aed, total_credit_aed) "
                "VALUES ('2026-04-15', '2026-04', 'Imbalanced test entry', "
                "        'manual:tester', 'manual', 'tester', "
                "        100.00, 99.99)",
            ),
        )
    assert "dr_equals_cr" in str(exc.value).lower() or "check" in str(exc.value).lower()
    db_session.rollback()


def test_short_narration_rejected(db_session: Session) -> None:
    _seed_period(db_session)
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO ledger.journal_entries "
                "(date, period, narration, source, source_kind, posted_by, "
                " total_debit_aed, total_credit_aed) "
                "VALUES ('2026-04-15', '2026-04', 'short', "
                "        'manual:tester', 'manual', 'tester', "
                "        50.00, 50.00)",
            ),
        )
    db_session.rollback()


def test_journal_line_debit_xor_credit(db_session: Session) -> None:
    _seed_period(db_session)
    je_id = db_session.execute(
        text(
            "INSERT INTO ledger.journal_entries "
            "(date, period, narration, source, source_kind, posted_by, "
            " total_debit_aed, total_credit_aed) "
            "VALUES ('2026-04-15', '2026-04', 'Both sides bad test', "
            "        'manual:tester', 'manual', 'tester', "
            "        10.00, 10.00) RETURNING je_id",
        ),
    ).scalar_one()
    # Need a postable account row to FK against.
    db_session.execute(
        text(
            "INSERT INTO master.chart_of_accounts "
            "(code, name, type, normal_balance, statement, is_postable, "
            " yaml_version, effective_from) "
            "VALUES ('1010','Cash test','asset','debit','BS',true,1,'2026-05-01') "
            "ON CONFLICT (code) DO NOTHING",
        ),
    )
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO ledger.journal_lines "
                "(je_id, account_code, debit_aed, credit_aed) "
                "VALUES (:je, '1010', 10.00, 10.00)",
            ),
            {"je": je_id},
        )
    db_session.rollback()


def test_period_format_check(db_session: Session) -> None:
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO master.periods (period, status, opened_at) "
                "VALUES ('2026-13', 'OPEN', NOW())",
            ),
        )
    db_session.rollback()


def test_attachment_policy_constraint(db_session: Session) -> None:
    _seed_period(db_session)
    # attachment_required=true but no url and no override reason → reject.
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO ledger.journal_entries "
                "(date, period, narration, source, source_kind, posted_by, "
                " total_debit_aed, total_credit_aed, attachment_required) "
                "VALUES ('2026-04-15', '2026-04', 'Big manual JE no doc', "
                "        'manual:cfo', 'manual', 'cfo', "
                "        60000.00, 60000.00, true)",
            ),
        )
    db_session.rollback()


def test_reopen_reason_minimum_length(db_session: Session) -> None:
    _seed_period(db_session)
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO audit.period_close_log "
                "(period, action, actor, reason) "
                "VALUES ('2026-04','REOPEN','cfo','too short')",
            ),
        )
    db_session.rollback()
