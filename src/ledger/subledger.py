"""Sub-ledger registry.

Sub-ledgers are append-only entry logs that mirror per-key activity for a
specific GL control account (or pair of contra accounts). The registry
dispatches each posted journal line to the right sub-ledger so the GL and
the sub-ledger stay in lockstep inside the same transaction.

Per ``docs/chart_of_accounts.md``:

| Sub-ledger        | Control account(s)              | Key field                |
|-------------------|---------------------------------|--------------------------|
| student_wallet    | 2050                            | student_id               |
| tutor_payable     | 2020 (PKR), 2030 (AED)          | tutor_id                 |
| fixed_asset       | 1111/1112, 1113/1114, 1115/1116 | asset_id                 |
| prepaid           | 1051, 1052                      | prepaid_id               |
| intangible        | 1121, 1122, 1123                | intangible_id            |
| sanction_memo     | 2060, 9010                      | sanction_request_id      |

A reconciliation routine for each sub-ledger compares its sum to the GL
control account balance and is the gate that period close runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

from src.core.money import ZERO_AED, aed
from src.ledger.coa import SubLedgerName

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.ledger.posting import JournalLineDraft


# ---------------------------------------------------------------------------
# Reconciliation result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReconciliationResult:
    sub_ledger: str
    matches: bool
    gl_balance: Decimal
    sub_ledger_sum: Decimal
    diff: Decimal
    per_key_diffs: dict[str, Decimal]


# ---------------------------------------------------------------------------
# Sub-ledger protocol
# ---------------------------------------------------------------------------


class SubLedger(Protocol):
    """Concrete sub-ledger interface (Protocol, structural typing)."""

    name: SubLedgerName
    control_accounts: tuple[str, ...]
    key_field: str

    def apply_line(
        self,
        session: Session,
        *,
        je_id: int,
        line_id: int,
        period: str,
        effective_date: date,
        line: JournalLineDraft,
    ) -> None:
        """Append the per-key sub-ledger row for *line*."""

    def row_exists(self, session: Session, key: str | int) -> bool:
        """Does the given key exist in the master table this sub-ledger guards?"""

    def balance(
        self,
        session: Session,
        key: str | int,
        *,
        as_of: date | None = None,
    ) -> Decimal:
        """Per-key running balance (signed AED, normalised to control side)."""

    def reconcile_to_gl(
        self,
        session: Session,
        *,
        as_of: date | None = None,
    ) -> ReconciliationResult:
        """Compare GL control balance to sum of sub-ledger entries."""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class SubLedgerRegistry:
    """Holds one concrete sub-ledger per :class:`SubLedgerName`."""

    def __init__(self) -> None:
        self._by_name: dict[SubLedgerName, SubLedger] = {}

    def register(self, sl: SubLedger) -> None:
        self._by_name[sl.name] = sl

    def get(self, name: SubLedgerName) -> SubLedger:
        try:
            return self._by_name[name]
        except KeyError:
            raise KeyError(f"sub-ledger {name.value} not registered") from None

    def has(self, name: SubLedgerName) -> bool:
        return name in self._by_name

    def all(self) -> list[SubLedger]:
        return list(self._by_name.values())


def build_default_registry() -> SubLedgerRegistry:
    """Wire up every concrete sub-ledger.

    Call this once at startup (or per test fixture). Importing the concrete
    classes here keeps the registry as the single source of truth and avoids
    circular imports.
    """
    from src.subledgers.fixed_asset import FixedAssetSubLedger
    from src.subledgers.intangible import IntangibleSubLedger
    from src.subledgers.prepaid import PrepaidSubLedger
    from src.subledgers.sanction_memo import SanctionMemoSubLedger
    from src.subledgers.student_wallet import StudentWalletSubLedger
    from src.subledgers.tutor_payable import TutorPayableSubLedger

    reg = SubLedgerRegistry()
    reg.register(StudentWalletSubLedger())
    reg.register(TutorPayableSubLedger())
    reg.register(FixedAssetSubLedger())
    reg.register(PrepaidSubLedger())
    reg.register(IntangibleSubLedger())
    reg.register(SanctionMemoSubLedger())
    return reg


# ---------------------------------------------------------------------------
# Helpers shared by concrete sub-ledgers
# ---------------------------------------------------------------------------


def signed_delta(line: JournalLineDraft, *, side: str) -> Decimal:
    """Compute the *signed* delta this line contributes to the sub-ledger.

    ``side`` is ``'credit'`` for credit-normal control accounts (liabilities,
    e.g. 2050, 2020), ``'debit'`` for debit-normal control accounts (assets,
    e.g. 1111). Sub-ledger sum should equal the GL balance under the account's
    natural sign.
    """
    d = aed(line.debit_aed)
    c = aed(line.credit_aed)
    if side == "credit":
        return c - d  # credits grow a credit-normal balance
    return d - c  # debits grow a debit-normal balance


def zero_diff(gl: Decimal, sl: Decimal) -> Decimal:
    return aed(gl) - aed(sl)


__all__ = [
    "ZERO_AED",
    "ReconciliationResult",
    "SubLedger",
    "SubLedgerRegistry",
    "build_default_registry",
    "signed_delta",
    "zero_diff",
]
