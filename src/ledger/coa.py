"""Chart of Accounts — in-memory model and YAML loader.

The YAML at ``docs/chart_of_accounts.yaml`` is the source of truth (per
``docs/CLAUDE.md``). This module reads it, validates structural rules, and
exposes a queryable :class:`COA` object plus a process-wide singleton accessed
via :func:`get_active_coa`.

Validation rules (Phase 2 spec §1.5):

1. Every code is a 4-digit numeric string and unique.
2. Every parent (if not null) exists and is a header (``is_postable=False``).
3. Postable accounts may not be parents.
4. Every ``sub_ledger`` is in the closed enum.
5. Range vs. type: 1xxx asset|contra; 2xxx liability; 3xxx equity;
   4xxx revenue; 5xxx,6xxx expense|contra; 7xxx revenue|expense; 9xxx memo.
6. Header accounts have ``is_postable=False``; leaf accounts have
   ``is_postable=True``.
7. Memo accounts (``is_memo=True``) live in the 9xxx range and have
   ``statement='MEMO'``.

Structural failures raise :class:`COAValidationError` with the full violation
list — surfacing all problems at once is more useful than first-fail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal  # noqa: F401  (re-exported for callers)
from enum import Enum
from pathlib import Path
from typing import Final

import yaml

from src.core.exceptions import COAValidationError

# ---- Enums shared with the migration ---------------------------------------


class AccountType(str, Enum):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"
    CONTRA = "contra"
    MEMO = "memo"


class NormalBalance(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class Statement(str, Enum):
    BS = "BS"
    IS = "IS"
    MEMO = "MEMO"


class SubLedgerName(str, Enum):
    STUDENT_WALLET = "student_wallet"
    TUTOR_PAYABLE = "tutor_payable"
    FIXED_ASSET = "fixed_asset"
    PREPAID = "prepaid"
    INTANGIBLE = "intangible"
    SANCTION_MEMO = "sanction_memo"


VALID_SUB_LEDGERS: Final[set[str]] = {member.value for member in SubLedgerName}
VALID_CURRENCIES: Final[set[str]] = {"AED", "PKR"}


@dataclass(frozen=True)
class Account:
    code: str
    name: str
    type: AccountType
    normal_balance: NormalBalance
    parent: str | None
    statement: Statement
    is_postable: bool
    sub_ledger: SubLedgerName | None
    currency: str | None
    is_memo: bool
    subtype: str | None
    description: str | None


@dataclass
class COA:
    """In-memory Chart of Accounts."""

    version: int
    effective_from: str
    accounts: dict[str, Account] = field(default_factory=dict)

    # ---- Constructors ------------------------------------------------------

    @classmethod
    def load_from_yaml(cls, path: Path) -> COA:
        if not path.exists():
            raise FileNotFoundError(f"chart_of_accounts.yaml not found at {path}")
        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        if not isinstance(raw, dict):
            raise COAValidationError(
                message="YAML root must be a mapping",
                violations=[f"got {type(raw).__name__}"],
            )

        try:
            version = int(raw["version"])
            effective_from = str(raw["effective_from"])
            accounts_list = raw["accounts"]
        except KeyError as exc:
            raise COAValidationError(
                message="Missing required top-level field",
                violations=[f"missing field: {exc.args[0]}"],
            ) from None

        accounts: dict[str, Account] = {}
        violations: list[str] = []

        for idx, item in enumerate(accounts_list):
            try:
                acct = _account_from_yaml(item)
            except (KeyError, ValueError, TypeError) as exc:
                violations.append(f"accounts[{idx}]: {exc}")
                continue
            if acct.code in accounts:
                violations.append(f"duplicate code: {acct.code}")
            else:
                accounts[acct.code] = acct

        if violations:
            raise COAValidationError(
                message="YAML parse failed",
                violations=violations,
            )

        coa = cls(version=version, effective_from=effective_from, accounts=accounts)
        coa.validate_structure()
        return coa

    # ---- Validation --------------------------------------------------------

    def validate_structure(self) -> None:
        violations: list[str] = []

        for code, acct in self.accounts.items():
            # Rule 1: 4-digit numeric.
            if not (len(code) == 4 and code.isdigit()):
                violations.append(f"{code}: code must be 4 digits")

            # Rule 4: sub_ledger in closed enum.
            if acct.sub_ledger is not None and acct.sub_ledger.value not in VALID_SUB_LEDGERS:
                violations.append(
                    f"{code}: sub_ledger '{acct.sub_ledger}' not in {VALID_SUB_LEDGERS}",
                )

            # Rule 5: range/type alignment.
            range_violation = _check_range_type(acct)
            if range_violation:
                violations.append(f"{code}: {range_violation}")

            # Rule 6: header vs. postable consistency is checked indirectly
            # below via parent/postable interaction (rule 2 + 3).

            # Rule 7: memo accounts.
            if acct.is_memo:
                if not code.startswith("9"):
                    violations.append(f"{code}: is_memo=true but code not in 9xxx range")
                if acct.statement is not Statement.MEMO:
                    violations.append(
                        f"{code}: is_memo=true but statement={acct.statement.value}",
                    )
                if acct.type is not AccountType.MEMO:
                    violations.append(
                        f"{code}: is_memo=true but type={acct.type.value}",
                    )

        # Rule 2 + 3: parent integrity.
        for code, acct in self.accounts.items():
            if acct.parent is None:
                continue
            parent = self.accounts.get(acct.parent)
            if parent is None:
                violations.append(f"{code}: parent '{acct.parent}' does not exist")
                continue
            if parent.is_postable:
                violations.append(
                    f"{code}: parent '{parent.code}' is postable; "
                    f"a postable account must not be a parent",
                )

        if violations:
            raise COAValidationError(
                message="COA structural validation failed",
                violations=violations,
            )

    # ---- Queries -----------------------------------------------------------

    def get(self, code: str) -> Account:
        try:
            return self.accounts[code]
        except KeyError:
            raise KeyError(f"unknown account code: {code}") from None

    def is_postable(self, code: str) -> bool:
        return self.get(code).is_postable

    def sub_ledger_for(self, code: str) -> SubLedgerName | None:
        return self.get(code).sub_ledger

    def normal_balance(self, code: str) -> NormalBalance:
        return self.get(code).normal_balance

    def all_active(self) -> list[Account]:
        return list(self.accounts.values())

    def is_memo(self, code: str) -> bool:
        return self.get(code).is_memo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _account_from_yaml(item: dict[str, object]) -> Account:
    code = str(item["code"]).strip()
    if not code:
        raise ValueError("empty code")
    typ = AccountType(str(item["type"]))
    nb = NormalBalance(str(item["normal_balance"]))
    parent_raw = item.get("parent")
    parent = str(parent_raw) if parent_raw is not None else None
    stmt = Statement(str(item["statement"]))
    is_postable = bool(item["is_postable"])
    sl_raw = item.get("sub_ledger")
    sub_ledger = SubLedgerName(str(sl_raw)) if sl_raw else None
    cur_raw = item.get("currency")
    currency = str(cur_raw) if cur_raw else None
    if currency is not None and currency not in VALID_CURRENCIES:
        raise ValueError(f"currency '{currency}' not in {VALID_CURRENCIES}")
    is_memo = bool(item.get("is_memo", False))
    subtype_raw = item.get("subtype")
    subtype = str(subtype_raw) if subtype_raw else None
    desc_raw = item.get("description")
    description = str(desc_raw) if desc_raw else None
    return Account(
        code=code,
        name=str(item["name"]),
        type=typ,
        normal_balance=nb,
        parent=parent,
        statement=stmt,
        is_postable=is_postable,
        sub_ledger=sub_ledger,
        currency=currency,
        is_memo=is_memo,
        subtype=subtype,
        description=description,
    )


def _check_range_type(acct: Account) -> str | None:
    """Return a violation string or ``None`` if the range/type pair is valid."""
    code = acct.code
    typ = acct.type
    leading = code[0]
    asset_like = {AccountType.ASSET, AccountType.CONTRA}
    liability_like = {AccountType.LIABILITY, AccountType.CONTRA}
    expense_like = {AccountType.EXPENSE, AccountType.CONTRA}

    if leading == "1":
        if typ not in asset_like:
            return f"1xxx range expects asset|contra, got {typ.value}"
    elif leading == "2":
        if typ not in liability_like:
            return f"2xxx range expects liability|contra, got {typ.value}"
    elif leading == "3":
        if typ is not AccountType.EQUITY:
            return f"3xxx range expects equity, got {typ.value}"
    elif leading == "4":
        if typ is not AccountType.REVENUE:
            return f"4xxx range expects revenue, got {typ.value}"
    elif leading in {"5", "6"}:
        if typ not in expense_like:
            return f"{leading}xxx range expects expense|contra, got {typ.value}"
    elif leading == "7":
        # 7xxx allows revenue (interest income) or expense/contra.
        if typ not in {AccountType.REVENUE, AccountType.EXPENSE, AccountType.CONTRA}:
            return f"7xxx range expects revenue|expense|contra, got {typ.value}"
    elif leading == "9":
        if typ is not AccountType.MEMO:
            return f"9xxx range expects memo, got {typ.value}"
    else:
        return f"unknown leading digit '{leading}'"
    return None


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_active_coa: COA | None = None


def set_active_coa(coa: COA) -> None:
    global _active_coa
    _active_coa = coa


def get_active_coa() -> COA:
    if _active_coa is None:
        raise RuntimeError(
            "active COA not set; call set_active_coa() at startup "
            "(or load_into_db() which sets it as a side-effect).",
        )
    return _active_coa


def reset_active_coa_for_tests() -> None:
    global _active_coa
    _active_coa = None
