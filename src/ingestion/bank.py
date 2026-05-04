"""Bank statement CSV parser.

Different banks ship CSVs with different column names. The parser takes a
``BankColumnMap`` so adding a new bank is a config change, not a code
change. Output rows are normalised to ``BankTransaction`` records.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import StringIO

from src.core.money import aed


@dataclass(frozen=True)
class BankColumnMap:
    """Maps the bank-specific column names onto our normalised fields."""

    date: str
    amount: str
    description: str
    balance: str | None = None
    reference: str | None = None
    date_format: str = "%Y-%m-%d"
    # Some banks emit credits/debits in separate columns instead of a signed
    # ``amount``. Set these when applicable; the parser sums them.
    credit_column: str | None = None
    debit_column: str | None = None


@dataclass(frozen=True)
class BankTransaction:
    date: date
    amount_aed: Decimal  # signed: positive = credit / inflow, negative = debit
    description: str
    reference: str | None
    balance_after: Decimal | None


def parse_bank_csv(
    csv_text: str,
    column_map: BankColumnMap,
) -> Iterable[BankTransaction]:
    """Yield :class:`BankTransaction` for each row in *csv_text*."""
    reader = csv.DictReader(StringIO(csv_text))
    for row in reader:
        try:
            txn_date = _parse_date(row[column_map.date], column_map.date_format)
            amount = _amount(row, column_map)
            description = row.get(column_map.description, "").strip()
            reference = row.get(column_map.reference) if column_map.reference else None
            balance = (
                aed(row[column_map.balance])
                if column_map.balance and row.get(column_map.balance)
                else None
            )
        except (KeyError, ValueError) as exc:
            raise BankCsvParseError(f"row parse failed: {exc}; row={row}") from exc
        yield BankTransaction(
            date=txn_date,
            amount_aed=amount,
            description=description,
            reference=reference,
            balance_after=balance,
        )


class BankCsvParseError(ValueError):
    """Raised on a malformed CSV row. The row is preserved in the message."""


def _amount(row: dict[str, str], cm: BankColumnMap) -> Decimal:
    if cm.credit_column or cm.debit_column:
        cred = aed(row.get(cm.credit_column or "", "0") or "0")
        deb = aed(row.get(cm.debit_column or "", "0") or "0")
        return cred - deb
    raw = row.get(cm.amount, "0").replace(",", "")
    return aed(raw)


def _parse_date(raw: str, fmt: str) -> date:
    from datetime import datetime as _dt

    return _dt.strptime(raw.strip(), fmt).date()
