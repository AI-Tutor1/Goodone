"""Smoke tests for ``tests/factories``.

Each factory must produce a valid object on ``.build()`` with no kwargs.
This guards against silent breakage when domain models grow new
required fields.
"""

from __future__ import annotations

from decimal import Decimal

from src.core.money import ZERO_AED
from src.ledger.coa import AccountType, NormalBalance
from src.ledger.posting import JournalEntryDraft, JournalLineDraft
from tests.factories import (
    AccountFactory,
    CreditLineDraftFactory,
    FxRateFactory,
    HeaderAccountFactory,
    JournalEntryDraftFactory,
    JournalLineDraftFactory,
    ManualFxRateFactory,
    StudentFactory,
    TutorFactory,
    WalletAccountFactory,
)


def test_account_factory_default_is_a_revenue_leaf() -> None:
    a = AccountFactory.build()
    assert a.type is AccountType.REVENUE
    assert a.normal_balance is NormalBalance.CREDIT
    assert a.is_postable is True
    assert a.code == "4010"


def test_wallet_factory_has_student_wallet_subledger() -> None:
    a = WalletAccountFactory.build()
    assert a.code == "2050"
    assert a.sub_ledger == "student_wallet"


def test_header_factory_is_not_postable() -> None:
    a = HeaderAccountFactory.build()
    assert a.is_postable is False
    assert a.parent is None


def test_journal_line_default_is_a_balanced_debit() -> None:
    line = JournalLineDraftFactory.build()
    assert isinstance(line, JournalLineDraft)
    assert line.account_code == "1010"
    assert line.debit_aed == Decimal("100.00")
    assert line.credit_aed == ZERO_AED


def test_credit_line_factory_mirrors_default() -> None:
    line = CreditLineDraftFactory.build()
    assert line.account_code == "4010"
    assert line.credit_aed == Decimal("100.00")
    assert line.debit_aed == ZERO_AED


def test_journal_entry_default_is_balanced() -> None:
    je = JournalEntryDraftFactory.build()
    assert isinstance(je, JournalEntryDraft)
    debit = sum((line.debit_aed for line in je.lines), ZERO_AED)
    credit = sum((line.credit_aed for line in je.lines), ZERO_AED)
    assert debit == credit
    assert je.source_kind == "manual"


def test_student_factory_returns_dict_with_required_keys() -> None:
    s = StudentFactory.build()
    assert {"display_id", "full_name", "email", "country", "status"} <= set(s.keys())
    assert s["display_id"].startswith("S-")


def test_tutor_factory_pkr_payment_currency_default() -> None:
    t = TutorFactory.build()
    assert t["payment_currency"] == "PKR"
    assert t["display_id"].startswith("T-")


def test_fx_rate_factory_default_is_aed_pkr_ecb() -> None:
    fx = FxRateFactory.build()
    assert fx["base"] == "AED"
    assert fx["quote"] == "PKR"
    assert fx["source"] == "ECB"


def test_manual_fx_rate_factory_marks_source_manual() -> None:
    fx = ManualFxRateFactory.build()
    assert fx["source"] == "manual"
