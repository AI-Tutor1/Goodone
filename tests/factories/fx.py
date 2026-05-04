"""Factories for FX rate dicts (``ledger.fx_rates``).

Produces dicts so tests can ``INSERT`` them via raw SQL or feed them to
the FX ingestion adapter. AED is the functional currency — by convention
we hold ``base="AED", quote="PKR"`` and store the rate as 1 AED = N PKR.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import factory


class FxRateFactory(factory.DictFactory):
    rate_date = factory.LazyFunction(date.today)
    base = "AED"
    quote = "PKR"
    rate = Decimal("76.50000000")
    source = "ECB"


class ManualFxRateFactory(FxRateFactory):
    """An override row — same shape but flagged as ``manual`` for audit."""

    source = "manual"
