"""Reusable factory-boy factories for the unit + integration suites.

Public exports follow the ``XFactory`` convention. All factories use
factory-boy's ``Factory`` (in-memory) backend — none of them touch a DB.
Persistence is the integration suite's job; factories produce shapes.

Examples:

    je = JournalEntryDraftFactory.build(
        narration="Custom narration", lines=[
            JournalLineDraftFactory.build(account_code="2050", credit_aed=aed(50)),
            JournalLineDraftFactory.build(account_code="1010", debit_aed=aed(50)),
        ],
    )

    student = StudentFactory.build(country="PK")
"""

from tests.factories.coa import (
    AccountFactory,
    HeaderAccountFactory,
    WalletAccountFactory,
)
from tests.factories.fx import FxRateFactory, ManualFxRateFactory
from tests.factories.journals import (
    CreditLineDraftFactory,
    JournalEntryDraftFactory,
    JournalLineDraftFactory,
)
from tests.factories.people import StudentFactory, TutorFactory

__all__ = [
    "AccountFactory",
    "CreditLineDraftFactory",
    "FxRateFactory",
    "HeaderAccountFactory",
    "JournalEntryDraftFactory",
    "JournalLineDraftFactory",
    "ManualFxRateFactory",
    "StudentFactory",
    "TutorFactory",
    "WalletAccountFactory",
]
