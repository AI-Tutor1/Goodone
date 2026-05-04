"""Unit tests for the bank CSV parser."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from src.ingestion.bank import BankColumnMap, BankCsvParseError, parse_bank_csv


def test_signed_amount_column() -> None:
    csv_text = "Date,Amount,Description\n2026-04-15,1500.00,Wallet topup\n"
    cm = BankColumnMap(date="Date", amount="Amount", description="Description")
    [txn] = list(parse_bank_csv(csv_text, cm))
    assert txn.date == date(2026, 4, 15)
    assert txn.amount_aed == Decimal("1500.00")
    assert txn.description == "Wallet topup"


def test_separate_credit_debit_columns() -> None:
    csv_text = (
        "Date,Credit,Debit,Description\n2026-04-15,1500.00,0.00,Topup\n2026-04-16,0,200.00,Refund\n"
    )
    cm = BankColumnMap(
        date="Date",
        amount="",  # ignored
        description="Description",
        credit_column="Credit",
        debit_column="Debit",
    )
    txns = list(parse_bank_csv(csv_text, cm))
    assert txns[0].amount_aed == Decimal("1500.00")
    assert txns[1].amount_aed == Decimal("-200.00")


def test_thousands_separator_stripped() -> None:
    csv_text = 'Date,Amount,Description\n2026-04-15,"1,500.00",Topup\n'
    cm = BankColumnMap(date="Date", amount="Amount", description="Description")
    [txn] = list(parse_bank_csv(csv_text, cm))
    assert txn.amount_aed == Decimal("1500.00")


def test_alternate_date_format() -> None:
    csv_text = "Date,Amount,Description\n15/04/2026,100,X\n"
    cm = BankColumnMap(
        date="Date",
        amount="Amount",
        description="Description",
        date_format="%d/%m/%Y",
    )
    [txn] = list(parse_bank_csv(csv_text, cm))
    assert txn.date == date(2026, 4, 15)


def test_malformed_row_raises() -> None:
    csv_text = "Date,Amount,Description\nnot-a-date,100,X\n"
    cm = BankColumnMap(date="Date", amount="Amount", description="Description")
    with pytest.raises(BankCsvParseError):
        list(parse_bank_csv(csv_text, cm))
