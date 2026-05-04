"""COA loader unit tests (no DB).

Covers the validation rules from ``src/ledger/coa.py`` docstring:

* YAML round-trip from the real ``docs/chart_of_accounts.yaml``
* Range/type checks
* Parent integrity
* Postable-leaf rule
* Memo (9xxx) accounts
* Idempotent reload (separate test for DB upsert)
* Missing-file behavior
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.core.exceptions import COAValidationError
from src.ledger.coa import COA, AccountType, Statement, SubLedgerName


def test_load_real_yaml_succeeds(coa_yaml_path: Path) -> None:
    coa = COA.load_from_yaml(coa_yaml_path)
    # Spot-checks from chart_of_accounts.yaml.
    assert coa.version >= 2  # bumped when 9010 was added
    assert coa.get("1010").name.startswith("Cash and Bank")
    assert coa.get("2050").sub_ledger is SubLedgerName.STUDENT_WALLET
    assert coa.get("9010").is_memo is True
    assert coa.get("9010").statement is Statement.MEMO


def test_postable_count_reasonable(coa_yaml_path: Path) -> None:
    coa = COA.load_from_yaml(coa_yaml_path)
    postable = [a for a in coa.all_active() if a.is_postable]
    headers = [a for a in coa.all_active() if not a.is_postable]
    assert len(postable) > 30, "expected many postable leaf accounts"
    assert len(headers) >= 8, "expected several header accounts"


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        COA.load_from_yaml(tmp_path / "nope.yaml")


def _write_yaml(tmp_path: Path, data: dict[str, object]) -> Path:
    path = tmp_path / "coa.yaml"
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh)
    return path


def _base_yaml() -> dict[str, object]:
    return {
        "version": 1,
        "effective_from": "2026-05-01",
        "accounts": [
            {
                "code": "1000",
                "name": "Current Assets",
                "type": "asset",
                "normal_balance": "debit",
                "parent": None,
                "statement": "BS",
                "is_postable": False,
                "sub_ledger": None,
            },
            {
                "code": "1010",
                "name": "Cash AED",
                "type": "asset",
                "normal_balance": "debit",
                "parent": "1000",
                "statement": "BS",
                "is_postable": True,
                "sub_ledger": None,
                "currency": "AED",
            },
        ],
    }


def test_parent_must_exist(tmp_path: Path) -> None:
    data = _base_yaml()
    data["accounts"][1]["parent"] = "9999"  # type: ignore[index]
    with pytest.raises(COAValidationError) as exc:
        COA.load_from_yaml(_write_yaml(tmp_path, data))
    assert any("does not exist" in v for v in exc.value.violations)


def test_postable_account_cannot_be_parent(tmp_path: Path) -> None:
    data = _base_yaml()
    # Make 1000 postable and keep 1010 as its child — a postable parent.
    data["accounts"][0]["is_postable"] = True  # type: ignore[index]
    with pytest.raises(COAValidationError) as exc:
        COA.load_from_yaml(_write_yaml(tmp_path, data))
    assert any("postable" in v.lower() for v in exc.value.violations)


def test_range_type_mismatch_caught(tmp_path: Path) -> None:
    data = _base_yaml()
    # 1010 declared as a liability — wrong range.
    data["accounts"][1]["type"] = "liability"  # type: ignore[index]
    with pytest.raises(COAValidationError) as exc:
        COA.load_from_yaml(_write_yaml(tmp_path, data))
    assert any("1xxx range" in v for v in exc.value.violations)


def test_duplicate_code_caught(tmp_path: Path) -> None:
    data = _base_yaml()
    accounts: list[dict[str, object]] = data["accounts"]  # type: ignore[assignment]
    accounts.append(dict(accounts[1]))  # duplicate "1010"
    with pytest.raises(COAValidationError) as exc:
        COA.load_from_yaml(_write_yaml(tmp_path, data))
    assert any("duplicate" in v for v in exc.value.violations)


def test_memo_account_must_be_9xxx_with_memo_statement(tmp_path: Path) -> None:
    data = _base_yaml()
    accounts: list[dict[str, object]] = data["accounts"]  # type: ignore[assignment]
    accounts.append(
        {
            "code": "1099",
            "name": "Bad memo",
            "type": "memo",
            "normal_balance": "debit",
            "parent": "1000",
            "statement": "BS",
            "is_postable": True,
            "sub_ledger": None,
            "is_memo": True,
        },
    )
    with pytest.raises(COAValidationError) as exc:
        COA.load_from_yaml(_write_yaml(tmp_path, data))
    msg = " ".join(exc.value.violations)
    assert "9xxx" in msg or "memo" in msg.lower()


def test_unknown_account_lookup_raises(coa_yaml_path: Path) -> None:
    coa = COA.load_from_yaml(coa_yaml_path)
    with pytest.raises(KeyError):
        coa.get("0000")


def test_normal_balance_lookup(coa_yaml_path: Path) -> None:
    coa = COA.load_from_yaml(coa_yaml_path)
    assert coa.normal_balance("1010").value == "debit"
    assert coa.normal_balance("2050").value == "credit"


def test_sub_ledger_lookup(coa_yaml_path: Path) -> None:
    coa = COA.load_from_yaml(coa_yaml_path)
    assert coa.sub_ledger_for("2020") is SubLedgerName.TUTOR_PAYABLE
    assert coa.sub_ledger_for("9010") is SubLedgerName.SANCTION_MEMO
    assert coa.sub_ledger_for("1010") is None


def test_exhaustive_range_pairs(coa_yaml_path: Path) -> None:
    """Confirm every account in the real YAML survives the range/type check."""
    # If load_from_yaml returns at all, validate_structure already passed.
    coa = COA.load_from_yaml(coa_yaml_path)
    # Sanity: we have accounts in every major range.
    leading = {a.code[0] for a in coa.all_active()}
    assert {"1", "2", "3", "4", "5", "6", "7", "9"} <= leading


def test_account_types_are_enum(coa_yaml_path: Path) -> None:
    coa = COA.load_from_yaml(coa_yaml_path)
    for acct in coa.all_active():
        assert isinstance(acct.type, AccountType)
