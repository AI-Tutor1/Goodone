"""Ledger exception hierarchy (see Phase 2 spec §1.13).

Every error carries machine-readable context fields so callers (API, tests)
can assert structurally without scraping strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class LedgerError(Exception):
    """Base for every ledger-engine error."""

    message: str = ""
    context: dict[str, object] = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - trivial
        if self.context:
            return f"{self.message} | context={self.context}"
        return self.message


# ---- ValidationError family ------------------------------------------------


@dataclass
class ValidationError(LedgerError):
    """Generic validation failure on a journal entry draft."""


@dataclass
class UnbalancedJournalError(ValidationError):
    debits: Decimal = Decimal("0.00")
    credits: Decimal = Decimal("0.00")


@dataclass
class AccountNotFoundError(ValidationError):
    account_code: str = ""


@dataclass
class AccountNotPostableError(ValidationError):
    account_code: str = ""


@dataclass
class MissingSubLedgerKeyError(ValidationError):
    account_code: str = ""
    sub_ledger: str = ""
    expected_key: str = ""


@dataclass
class DimensionRequiredError(ValidationError):
    account_code: str = ""
    dimension: str = ""


@dataclass
class NarrationTooShortError(ValidationError):
    pass


@dataclass
class LineShapeError(ValidationError):
    """A single journal_lines row violated the debit-XOR-credit rule."""


# ---- PeriodError family ----------------------------------------------------


@dataclass
class PeriodError(LedgerError):
    period: str = ""


@dataclass
class PeriodClosedError(PeriodError):
    pass


@dataclass
class PeriodNotFoundError(PeriodError):
    pass


@dataclass
class PeriodReopenReasonError(PeriodError):
    """Reopen attempted without (or with too-short) reason text."""


# ---- SubLedgerError family --------------------------------------------------


@dataclass
class SubLedgerError(LedgerError):
    sub_ledger: str = ""


@dataclass
class WalletNegativeError(SubLedgerError):
    student_id: str = ""
    current_balance: Decimal = Decimal("0.00")
    requested_delta: Decimal = Decimal("0.00")


@dataclass
class ReconciliationMismatchError(SubLedgerError):
    account_code: str = ""
    gl_balance: Decimal = Decimal("0.00")
    sub_ledger_sum: Decimal = Decimal("0.00")


# ---- Other -----------------------------------------------------------------


@dataclass
class ImmutabilityError(LedgerError):
    """An attempt was made to modify a posted journal."""


@dataclass
class ReversalError(LedgerError):
    je_id: int = 0


@dataclass
class COAValidationError(LedgerError):
    """The chart_of_accounts.yaml failed structural validation."""

    violations: list[str] = field(default_factory=list)
