"""Decimal money helpers — quantization, rounding, float-rejection."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.core.money import aed, fx_rate, pkr, round_aed


class TestAedConstructor:
    def test_str_input_quantizes_to_two_dp(self) -> None:
        assert aed("1820.83") == Decimal("1820.83")

    def test_int_input_quantizes_to_two_dp(self) -> None:
        assert aed(2500) == Decimal("2500.00")

    def test_decimal_input_passes_through(self) -> None:
        assert aed(Decimal("1916.665")) == Decimal("1916.67")  # half-up

    def test_half_up_rounding(self) -> None:
        # Decimal(0.005) ≠ exactly 0.005 due to float-binary; we use str.
        assert aed("0.005") == Decimal("0.01")
        assert aed("0.014") == Decimal("0.01")
        assert aed("0.015") == Decimal("0.02")

    def test_float_input_rejected(self) -> None:
        with pytest.raises(TypeError, match="never float"):
            aed(0.1)

    def test_canonical_penalty_example(self) -> None:
        # context.md §5: 46 / 60 × 2500 × 0.95 = 1820.833... → 1820.83
        prorated = Decimal("2500") * Decimal("46") / Decimal("60")
        net_pay = prorated * Decimal("0.95")
        assert aed(net_pay) == Decimal("1820.83")


class TestPkrConstructor:
    def test_pkr_quantization(self) -> None:
        assert pkr("123456.789") == Decimal("123456.79")


class TestFxRate:
    def test_fx_eight_dp(self) -> None:
        assert fx_rate("0.013157894") == Decimal("0.01315789")

    def test_fx_rejects_float(self) -> None:
        with pytest.raises(TypeError):
            fx_rate(0.013)


class TestRoundAed:
    def test_idempotent_on_already_quantized(self) -> None:
        x = Decimal("100.00")
        assert round_aed(x) == x
