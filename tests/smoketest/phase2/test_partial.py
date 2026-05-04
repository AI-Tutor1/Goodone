"""Phase-2 partial smoketest.

End-to-end:

1. Run the migration (handled by ``conftest.migrated_engine``).
2. Run ``scripts.seed_dev_data.seed`` against the DB.
3. Run ``PeriodService.close`` for ``2026-04``.
4. Snapshot trial balances + sub-ledger sums + a few key account balances.
5. Diff against the committed golden file at
   ``tests/fixtures/smoketest/phase2/expected.json``.

Marked ``smoketest`` so ``make smoketest`` runs only this test (and any
future Phase-N partial smoketests).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.ledger.period import PeriodService
from src.ledger.subledger import build_default_registry

pytestmark = [pytest.mark.smoketest, pytest.mark.integration]


GOLDEN_PATH = (
    Path(__file__).parent.parent.parent / "fixtures" / "smoketest" / "phase2" / "expected.json"
)


def test_phase2_partial_smoketest(db_session: Session, coa_yaml_path: Path) -> None:
    from scripts.seed_dev_data import seed

    summary = seed(db_session.connection())
    assert summary["students"] == 5
    assert summary["tutors"] == 3
    assert summary["topups"] == 5
    assert summary["refunds"] == 2
    assert summary["sessions"] == 40  # 19*2 + 2 penalty

    registry = build_default_registry()
    PeriodService(sub_ledgers=registry).close(db_session, "2026-04", by="cfo")

    snapshot = _snapshot(db_session)
    expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    # Spot-check exactly what the golden file commits.
    assert snapshot["period_status_after_close"] == expected["period_status_after_close"]
    assert snapshot["trial_balance_zero"] is True
    assert snapshot["je_count_after_seed"] == expected["je_count_after_seed"]

    for code, want in expected["balances"].items():
        assert snapshot["balances"][code] == want, (
            f"account {code} differs: got {snapshot['balances'][code]} want {want}"
        )

    # Per-student wallet balances.
    for display_id, want in expected["wallet_per_student_aed"].items():
        assert snapshot["wallet_per_student_aed"][display_id] == want, (
            f"wallet for {display_id} differs: got "
            f"{snapshot['wallet_per_student_aed'][display_id]} want {want}"
        )

    # Penalty JE byte-checked.
    pj = snapshot["penalty_case_journal"]
    expected_pj = expected["penalty_case_journal"]
    assert pj["lines"] == expected_pj["lines"]

    # Sub-ledger reconciliation must say "matches" everywhere.
    for sl_name, status in expected["subledger_reconciliation"].items():
        assert snapshot["subledger_reconciliation"][sl_name] == status


# ---------------------------------------------------------------------------


def _snapshot(session: Session) -> dict:
    je_count = int(
        session.execute(
            text("SELECT COUNT(*) FROM ledger.journal_entries WHERE status='POSTED'"),
        ).scalar_one(),
    )
    period_status = session.execute(
        text("SELECT status FROM master.periods WHERE period='2026-04'"),
    ).scalar_one()

    # Per-account sums (debit-credit netted in their natural sign).
    balances: dict[str, str] = {}
    for code in ["1010", "3010", "3020", "4010", "5010", "5020"]:
        balances[code] = str(_account_balance(session, code))
    balances["2050_total"] = str(_credit_normal(session, "2050"))
    balances["2020_total"] = str(_credit_normal(session, "2020"))

    # Per-student wallet
    wallet_rows = session.execute(
        text(
            "SELECT s.display_id, COALESCE(SUM(w.delta_aed), 0) AS bal "
            "FROM master.students s "
            "LEFT JOIN subledger.student_wallet_entries w "
            "  ON w.student_id = s.student_id "
            "GROUP BY s.display_id ORDER BY s.display_id",
        ),
    ).all()
    wallet_per_student = {row.display_id: str(_q(row.bal)) for row in wallet_rows}

    # Penalty JE
    penalty_je_id = session.execute(
        text(
            "SELECT je_id FROM ledger.journal_entries WHERE source_ref = 'SES-PENALTY-COST'",
        ),
    ).scalar_one()
    penalty_lines = session.execute(
        text(
            "SELECT account_code, debit_aed, credit_aed "
            "FROM ledger.journal_lines "
            "WHERE je_id = :id ORDER BY line_id",
        ),
        {"id": penalty_je_id},
    ).all()
    penalty_payload = {
        "source_ref": "SES-PENALTY-COST",
        "lines": [
            {
                "account_code": row.account_code,
                "debit_aed": str(_q(row.debit_aed)),
                "credit_aed": str(_q(row.credit_aed)),
            }
            for row in penalty_lines
        ],
    }

    # Sub-ledger reconciliation
    registry = build_default_registry()
    sub_status: dict[str, str] = {}
    for sl in registry.all():
        result = sl.reconcile_to_gl(session)
        sub_status[sl.name.value] = "matches" if result.matches else "mismatch"

    # Trial balance check
    tb = session.execute(
        text(
            "SELECT COALESCE(SUM(debit_aed), 0) = COALESCE(SUM(credit_aed), 0) "
            "FROM ledger.journal_lines",
        ),
    ).scalar_one()

    return {
        "period_status_after_close": period_status,
        "trial_balance_zero": bool(tb),
        "je_count_after_seed": je_count,
        "balances": balances,
        "wallet_per_student_aed": wallet_per_student,
        "penalty_case_journal": penalty_payload,
        "subledger_reconciliation": sub_status,
    }


def _account_balance(session: Session, code: str) -> Decimal:
    """Net debit-credit for a debit-normal account (credit-credit for credit-normal)."""
    debit_total = session.execute(
        text(
            "SELECT COALESCE(SUM(debit_aed - credit_aed), 0) "
            "FROM ledger.journal_lines WHERE account_code = :c",
        ),
        {"c": code},
    ).scalar_one()
    credit_total = session.execute(
        text(
            "SELECT COALESCE(SUM(credit_aed - debit_aed), 0) "
            "FROM ledger.journal_lines WHERE account_code = :c",
        ),
        {"c": code},
    ).scalar_one()
    # For 3xxx, 4xxx (credit-normal) we want the credit side; for 1xxx, 5xxx
    # we want the debit side. Pick the one that's positive.
    if code.startswith(("3", "4")):
        return _q(credit_total)
    return _q(debit_total)


def _credit_normal(session: Session, code: str) -> Decimal:
    return _q(
        session.execute(
            text(
                "SELECT COALESCE(SUM(credit_aed - debit_aed), 0) "
                "FROM ledger.journal_lines WHERE account_code = :c",
            ),
            {"c": code},
        ).scalar_one(),
    )


def _q(value: object) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))
