"""Pure-math tests for the payroll agent (no DB)."""

from __future__ import annotations

from decimal import Decimal

from src.agents.payroll import compute_payment


def test_full_session_no_penalty() -> None:
    c = compute_payment(
        tutor_rate_aed=Decimal("2500"),
        scheduled_minutes=60,
        conducted_minutes=60,
    )
    assert c.prorated_aed == Decimal("2500.00")
    assert c.net_pay_aed == Decimal("2500.00")
    assert c.penalty_aed == Decimal("0.00")


def test_threshold_52_min_no_penalty() -> None:
    c = compute_payment(
        tutor_rate_aed=Decimal("2500"),
        scheduled_minutes=60,
        conducted_minutes=52,
    )
    assert c.net_pay_aed == Decimal("2500.00")
    assert c.penalty_aed == Decimal("0.00")


def test_canonical_46_min_penalty() -> None:
    """Worked example from context.md §5: 46/60/2500 → 1820.83 net."""
    c = compute_payment(
        tutor_rate_aed=Decimal("2500"),
        scheduled_minutes=60,
        conducted_minutes=46,
    )
    assert c.prorated_aed == Decimal("1916.67")
    assert c.net_pay_aed == Decimal("1820.83")
    # Penalty balances to the cent (not the docs' 95.83 — see golden file note).
    assert c.penalty_aed == Decimal("95.84")
    assert c.net_pay_aed + c.penalty_aed == c.prorated_aed


def test_overtime_capped() -> None:
    c = compute_payment(
        tutor_rate_aed=Decimal("2500"),
        scheduled_minutes=60,
        conducted_minutes=90,
    )
    assert c.net_pay_aed == Decimal("2500.00")
    assert c.penalty_aed == Decimal("0.00")


def test_zero_minute_no_pay() -> None:
    c = compute_payment(
        tutor_rate_aed=Decimal("2500"),
        scheduled_minutes=60,
        conducted_minutes=0,
    )
    assert c.prorated_aed == Decimal("0.00")
    assert c.net_pay_aed == Decimal("0.00")
    assert c.penalty_aed == Decimal("0.00")


def test_thirty_minutes_penalty() -> None:
    c = compute_payment(
        tutor_rate_aed=Decimal("2500"),
        scheduled_minutes=60,
        conducted_minutes=30,
    )
    # 2500 * 30/60 = 1250 → 1250 * 0.95 = 1187.50
    assert c.prorated_aed == Decimal("1250.00")
    assert c.net_pay_aed == Decimal("1187.50")
    assert c.penalty_aed == Decimal("62.50")
