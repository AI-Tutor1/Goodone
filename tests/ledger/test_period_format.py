"""Unit tests for period.py helpers that don't need a DB."""

from __future__ import annotations

import pytest

from src.core.exceptions import PeriodError
from src.ledger.period import _validate_period_format, iter_months


@pytest.mark.parametrize("good", ["2026-04", "2024-01", "2099-12"])
def test_validate_format_accepts_good(good: str) -> None:
    _validate_period_format(good)  # no raise


@pytest.mark.parametrize(
    "bad",
    ["2026-13", "2026-00", "26-04", "2026/04", "2026-4", "abcd-ef", ""],
)
def test_validate_format_rejects_bad(bad: str) -> None:
    with pytest.raises(PeriodError):
        _validate_period_format(bad)


def test_iter_months_inclusive() -> None:
    assert list(iter_months("2026-01", "2026-04")) == [
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
    ]


def test_iter_months_year_boundary() -> None:
    assert list(iter_months("2025-11", "2026-02")) == [
        "2025-11",
        "2025-12",
        "2026-01",
        "2026-02",
    ]


def test_iter_months_single() -> None:
    assert list(iter_months("2026-04", "2026-04")) == ["2026-04"]
