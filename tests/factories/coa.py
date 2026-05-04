"""Factories for COA :class:`Account` objects.

Lighter-weight than building a full :class:`COA` — useful when a test
only needs to assert on classification helpers (``is_postable``,
``sub_ledger``) for a handful of accounts.
"""

from __future__ import annotations

import factory

from src.ledger.coa import Account, AccountType, NormalBalance, Statement


class AccountFactory(factory.Factory):
    """Default: a 4-digit revenue leaf in the 4xxx range."""

    class Meta:
        model = Account

    code = "4010"
    name = "Tutoring Revenue"
    type = AccountType.REVENUE
    normal_balance = NormalBalance.CREDIT
    parent = "4000"
    statement = Statement.IS
    is_postable = True
    sub_ledger = None
    currency = "AED"
    is_memo = False
    subtype = None
    description = None


class WalletAccountFactory(AccountFactory):
    """The ``2050`` student wallet liability — exercises the wallet sub-ledger."""

    code = "2050"
    name = "Student Wallets"
    type = AccountType.LIABILITY
    normal_balance = NormalBalance.CREDIT
    parent = "2000"
    statement = Statement.BS
    sub_ledger = "student_wallet"


class HeaderAccountFactory(AccountFactory):
    """Non-postable header — useful for negative-path tests
    (`AccountNotPostableError`)."""

    code = "4000"
    name = "Revenue (header)"
    parent = None
    is_postable = False
