"""Unit tests for subledger.py + the per-sub-ledger classify helpers (no DB)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.ledger.coa import SubLedgerName
from src.ledger.posting import JournalLineDraft
from src.ledger.subledger import SubLedgerRegistry, build_default_registry, signed_delta


def _line(*, debit: str = "0", credit: str = "0", code: str = "1010") -> JournalLineDraft:
    return JournalLineDraft(
        account_code=code,
        debit_aed=Decimal(debit),
        credit_aed=Decimal(credit),
    )


# ---- signed_delta ----------------------------------------------------------


def test_signed_delta_credit_normal() -> None:
    assert signed_delta(_line(credit="100.00"), side="credit") == Decimal("100.00")
    assert signed_delta(_line(debit="40.00"), side="credit") == Decimal("-40.00")


def test_signed_delta_debit_normal() -> None:
    assert signed_delta(_line(debit="100.00"), side="debit") == Decimal("100.00")
    assert signed_delta(_line(credit="40.00"), side="debit") == Decimal("-40.00")


# ---- registry --------------------------------------------------------------


def test_registry_has_six_sub_ledgers() -> None:
    reg = build_default_registry()
    names = {sl.name for sl in reg.all()}
    assert names == {
        SubLedgerName.STUDENT_WALLET,
        SubLedgerName.TUTOR_PAYABLE,
        SubLedgerName.FIXED_ASSET,
        SubLedgerName.PREPAID,
        SubLedgerName.INTANGIBLE,
        SubLedgerName.SANCTION_MEMO,
    }


def test_registry_lookup_by_name() -> None:
    reg = build_default_registry()
    sl = reg.get(SubLedgerName.STUDENT_WALLET)
    assert sl.key_field == "student_id"
    assert sl.control_accounts == ("2050",)


def test_registry_missing_raises() -> None:
    reg = SubLedgerRegistry()
    with pytest.raises(KeyError):
        reg.get(SubLedgerName.STUDENT_WALLET)


def test_registry_has() -> None:
    reg = build_default_registry()
    assert reg.has(SubLedgerName.TUTOR_PAYABLE) is True


# ---- classify helpers ------------------------------------------------------


def test_sanction_memo_classify_commit() -> None:
    from src.subledgers.sanction_memo import _classify

    line = _line(code="2060", debit="100.00")
    assert _classify(line) == "COMMIT"


def test_sanction_memo_classify_contra() -> None:
    from src.subledgers.sanction_memo import _classify

    line = _line(code="9010", credit="100.00")
    assert _classify(line) == "CONTRA"


def test_sanction_memo_classify_spend_reverse() -> None:
    from src.subledgers.sanction_memo import _classify

    debit_9010 = _line(code="9010", debit="100.00")
    credit_2060 = _line(code="2060", credit="100.00")
    assert _classify(debit_9010) == "SPEND_REVERSE"
    assert _classify(credit_2060) == "SPEND_REVERSE"


def test_intangible_classify() -> None:
    from src.subledgers.intangible import _classify

    cap_1121 = _line(code="1121", debit="2000.00")
    reclass_1122 = _line(code="1122", debit="48000.00")
    amort_1123 = _line(code="1123", credit="800.00")
    assert _classify(cap_1121) == ("CAPITALIZE", Decimal("2000.00"))
    assert _classify(reclass_1122) == ("RECLASS_TO_LAUNCHED", Decimal("48000.00"))
    assert _classify(amort_1123) == ("AMORTIZE", Decimal("800.00"))


def test_student_wallet_classify_inferred() -> None:
    from src.subledgers.student_wallet import _classify as wc

    topup = _line(code="2050", credit="100.00")
    consume = _line(code="2050", debit="50.00")
    assert wc(topup) == "TOPUP"
    assert wc(consume) == "CONSUME"


def test_student_wallet_classify_explicit() -> None:
    from src.subledgers.student_wallet import _classify as wc

    line = JournalLineDraft(
        account_code="2050",
        credit_aed=Decimal("0.01"),
        dimensions={"wallet_type": "ADJUST"},
    )
    assert wc(line) == "ADJUST"
