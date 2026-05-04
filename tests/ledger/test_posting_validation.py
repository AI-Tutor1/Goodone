"""Unit tests for the *pre-DB* validation steps in posting.py.

Anything that requires a real database lives in
``tests/db/test_posting_integration.py`` (marked ``integration``).
Here we exercise the pieces that depend only on the COA + draft objects.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.core.exceptions import (
    AccountNotFoundError,
    AccountNotPostableError,
    LineShapeError,
    NarrationTooShortError,
    UnbalancedJournalError,
    ValidationError,
)
from src.ledger.coa import COA
from src.ledger.posting import (
    JournalEntryDraft,
    JournalLineDraft,
    _balance_totals,
    _validate_attachment_policy,
    _validate_draft_shape,
    _validate_lines_against_coa,
)


@pytest.fixture(scope="module")
def coa(coa_yaml_path: Path) -> COA:
    return COA.load_from_yaml(coa_yaml_path)


def _good_draft(**overrides: object) -> JournalEntryDraft:
    """A balanced 2-line draft against real COA accounts."""
    base: dict[str, object] = {
        "date": date(2026, 4, 15),
        "narration": "Wallet topup test entry",  # >= 10 chars
        "source": "manual:tester",
        "source_kind": "manual",
        "posted_by": "tester",
        "lines": [
            JournalLineDraft(
                account_code="1010",
                debit_aed=Decimal("100.00"),
            ),
            JournalLineDraft(
                account_code="2050",
                credit_aed=Decimal("100.00"),
                sub_ledger_keys={"student_id": 1},
            ),
        ],
    }
    base.update(overrides)
    return JournalEntryDraft(**base)


# ---- Shape -----------------------------------------------------------------


def test_short_narration_rejected() -> None:
    with pytest.raises(NarrationTooShortError):
        _validate_draft_shape(_good_draft(narration="too short"))


def test_single_line_rejected() -> None:
    bad = _good_draft()
    bad = bad.model_copy(update={"lines": bad.lines[:1]})
    with pytest.raises(ValidationError):
        _validate_draft_shape(bad)


def test_both_debit_and_credit_on_one_line_rejected() -> None:
    line = JournalLineDraft(
        account_code="1010",
        debit_aed=Decimal("10.00"),
        credit_aed=Decimal("10.00"),
    )
    other = JournalLineDraft(account_code="2050", credit_aed=Decimal("0"))
    bad = _good_draft().model_copy(update={"lines": [line, other]})
    with pytest.raises(LineShapeError):
        _validate_draft_shape(bad)


def test_neither_debit_nor_credit_rejected() -> None:
    line = JournalLineDraft(account_code="1010")
    other = JournalLineDraft(account_code="2050", credit_aed=Decimal("10.00"))
    bad = _good_draft().model_copy(update={"lines": [line, other]})
    with pytest.raises(LineShapeError):
        _validate_draft_shape(bad)


def test_negative_amount_rejected() -> None:
    line = JournalLineDraft(account_code="1010", debit_aed=Decimal("-1.00"))
    other = JournalLineDraft(account_code="2050", credit_aed=Decimal("1.00"))
    bad = _good_draft().model_copy(update={"lines": [line, other]})
    with pytest.raises(LineShapeError):
        _validate_draft_shape(bad)


# ---- COA -------------------------------------------------------------------


def test_unknown_account_rejected(coa: COA) -> None:
    bad = _good_draft().model_copy(
        update={
            "lines": [
                JournalLineDraft(account_code="9999", debit_aed=Decimal("10.00")),
                JournalLineDraft(
                    account_code="2050",
                    credit_aed=Decimal("10.00"),
                    sub_ledger_keys={"student_id": 1},
                ),
            ],
        },
    )
    with pytest.raises(AccountNotFoundError) as exc:
        _validate_lines_against_coa(bad, coa)
    assert exc.value.account_code == "9999"


def test_non_postable_account_rejected(coa: COA) -> None:
    """1000 'Current Assets' is a header — is_postable=False."""
    bad = _good_draft().model_copy(
        update={
            "lines": [
                JournalLineDraft(account_code="1000", debit_aed=Decimal("10.00")),
                JournalLineDraft(
                    account_code="2050",
                    credit_aed=Decimal("10.00"),
                    sub_ledger_keys={"student_id": 1},
                ),
            ],
        },
    )
    with pytest.raises(AccountNotPostableError):
        _validate_lines_against_coa(bad, coa)


# ---- Balance ---------------------------------------------------------------


def test_balanced_passes() -> None:
    debit, credit = _balance_totals(_good_draft())
    assert debit == credit == Decimal("100.00")


def test_unbalanced_rejected() -> None:
    bad = _good_draft().model_copy(
        update={
            "lines": [
                JournalLineDraft(account_code="1010", debit_aed=Decimal("99.99")),
                JournalLineDraft(
                    account_code="2050",
                    credit_aed=Decimal("100.00"),
                    sub_ledger_keys={"student_id": 1},
                ),
            ],
        },
    )
    with pytest.raises(UnbalancedJournalError) as exc:
        _balance_totals(bad)
    assert exc.value.debits == Decimal("99.99")
    assert exc.value.credits == Decimal("100.00")


def test_decimal_no_drift() -> None:
    """Sum of three lines with awkward fractions still balances exactly."""
    draft = _good_draft().model_copy(
        update={
            "lines": [
                JournalLineDraft(account_code="5010", debit_aed=Decimal("1916.67")),
                JournalLineDraft(
                    account_code="2020",
                    credit_aed=Decimal("1820.83"),
                    sub_ledger_keys={"tutor_id": 1},
                ),
                JournalLineDraft(account_code="5020", credit_aed=Decimal("95.84")),
            ],
        },
    )
    debit, credit = _balance_totals(draft)
    assert debit == credit == Decimal("1916.67")


# ---- Attachment policy -----------------------------------------------------


def test_small_manual_no_attachment_ok() -> None:
    draft = _good_draft()
    assert _validate_attachment_policy(draft) is False


def test_large_manual_with_attachment_ok() -> None:
    draft = _good_draft().model_copy(
        update={
            "lines": [
                JournalLineDraft(account_code="1010", debit_aed=Decimal("60000.00")),
                JournalLineDraft(
                    account_code="2050",
                    credit_aed=Decimal("60000.00"),
                    sub_ledger_keys={"student_id": 1},
                ),
            ],
            "attachment_url": "https://attachments/foo.pdf",
        },
    )
    assert _validate_attachment_policy(draft) is True


def test_large_manual_with_override_reason_ok() -> None:
    long_reason = "audit trail to be reattached when the bank statement arrives next week"
    draft = _good_draft().model_copy(
        update={
            "lines": [
                JournalLineDraft(account_code="1010", debit_aed=Decimal("60000.00")),
                JournalLineDraft(
                    account_code="2050",
                    credit_aed=Decimal("60000.00"),
                    sub_ledger_keys={"student_id": 1},
                ),
            ],
            "attachment_url": None,
            "attachment_override_reason": long_reason,
        },
    )
    assert _validate_attachment_policy(draft) is True


def test_large_manual_no_attachment_no_reason_rejected() -> None:
    draft = _good_draft().model_copy(
        update={
            "lines": [
                JournalLineDraft(account_code="1010", debit_aed=Decimal("60000.00")),
                JournalLineDraft(
                    account_code="2050",
                    credit_aed=Decimal("60000.00"),
                    sub_ledger_keys={"student_id": 1},
                ),
            ],
        },
    )
    with pytest.raises(ValidationError):
        _validate_attachment_policy(draft)


def test_system_source_not_subject_to_attachment_threshold() -> None:
    draft = _good_draft().model_copy(
        update={
            "source": "system:revenue_agent",
            "source_kind": "system",
            "lines": [
                JournalLineDraft(account_code="1010", debit_aed=Decimal("999999.00")),
                JournalLineDraft(
                    account_code="2050",
                    credit_aed=Decimal("999999.00"),
                    sub_ledger_keys={"student_id": 1},
                ),
            ],
        },
    )
    assert _validate_attachment_policy(draft) is False
