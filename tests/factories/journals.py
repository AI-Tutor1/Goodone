"""Factories for ``JournalEntryDraft`` / ``JournalLineDraft``.

Every factory yields a *valid-by-default* object so tests don't have to
re-state the COA and balance constraints. Override fields per-test by
passing kwargs:

>>> JournalEntryDraftFactory.build(narration="Custom narration here")
>>> JournalLineDraftFactory.build(account_code="2050", debit_aed=aed(10))

The default JE is a tiny revenue recognition entry that's already
balanced (credit 4xxx revenue, debit 1010 cash) and uses a date in the
current operating period to avoid period-status hits.
"""

from __future__ import annotations

from datetime import date

import factory
from factory import LazyFunction

from src.core.money import aed
from src.ledger.posting import JournalEntryDraft, JournalLineDraft


class JournalLineDraftFactory(factory.Factory):
    """Default: a 100 AED debit on cash."""

    class Meta:
        model = JournalLineDraft

    account_code = "1010"
    debit_aed = LazyFunction(lambda: aed(100))
    credit_aed = LazyFunction(lambda: aed(0))
    sub_ledger_keys = factory.LazyFunction(dict)
    dimensions = factory.LazyFunction(dict)


class CreditLineDraftFactory(JournalLineDraftFactory):
    """Mirror of the default — a 100 AED credit to ``4010`` (revenue)."""

    account_code = "4010"
    debit_aed = LazyFunction(lambda: aed(0))
    credit_aed = LazyFunction(lambda: aed(100))


class JournalEntryDraftFactory(factory.Factory):
    """A balanced 2-line JE: cash debit ↔ revenue credit, AED 100."""

    class Meta:
        model = JournalEntryDraft

    date = LazyFunction(date.today)
    narration = "Factory-built journal entry for tests"
    source = "tests"
    source_kind = "manual"
    posted_by = "tests"
    attachment_url = None
    lines = factory.LazyFunction(
        lambda: [JournalLineDraftFactory.build(), CreditLineDraftFactory.build()],
    )
