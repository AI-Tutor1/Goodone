"""Money helpers.

Every monetary value in the calc core is a :class:`decimal.Decimal`. ``float``
is forbidden — see ``tests/test_no_float.py``.

Conventions:

* AED amounts: 2 decimal places, ``ROUND_HALF_UP``.
* PKR amounts (sub-ledger only): 2 decimal places, ``ROUND_HALF_UP``.
* FX rates: 8 decimal places, ``ROUND_HALF_UP``.

The ``aed`` / ``pkr`` constructors accept ``str | int | Decimal`` only — never
``float`` — and return a quantized ``Decimal``. Using ``str`` ensures the
caller's literal value (e.g. ``"1820.83"``) is preserved exactly.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Final

QUANT_AED: Final[Decimal] = Decimal("0.01")
QUANT_PKR: Final[Decimal] = Decimal("0.01")
QUANT_FX: Final[Decimal] = Decimal("0.00000001")
ZERO_AED: Final[Decimal] = Decimal("0.00")


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, str)):
        return Decimal(value)
    if isinstance(value, bool):  # pragma: no cover - bool is int but disallow explicitly
        raise TypeError("bool is not a valid money input")
    raise TypeError(
        f"Refusing to construct money from {type(value).__name__}; "
        "use str/int/Decimal only (never float)."
    )


def aed(value: object) -> Decimal:
    """Quantize *value* to AED (2dp, half-up). Rejects ``float``."""
    return _to_decimal(value).quantize(QUANT_AED, rounding=ROUND_HALF_UP)


def pkr(value: object) -> Decimal:
    """Quantize *value* to PKR (2dp, half-up). Rejects ``float``."""
    return _to_decimal(value).quantize(QUANT_PKR, rounding=ROUND_HALF_UP)


def fx_rate(value: object) -> Decimal:
    """Quantize *value* to an FX rate (8dp, half-up). Rejects ``float``."""
    return _to_decimal(value).quantize(QUANT_FX, rounding=ROUND_HALF_UP)


def round_aed(value: Decimal) -> Decimal:
    """Round an existing Decimal to AED scale."""
    return value.quantize(QUANT_AED, rounding=ROUND_HALF_UP)
