"""Shared hypothesis strategies + helpers for property-based tests.

These tests need a real Postgres (testcontainers); they're marked
``integration`` so ``make test`` skips them.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import hypothesis.strategies as st
import pytest

from src.ledger.posting import JournalEntryDraft, JournalLineDraft

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


def aed_amounts(min_value: int = 1, max_value: int = 100_000) -> st.SearchStrategy[Decimal]:
    """Random AED amounts to 2 dp, never zero."""
    return st.decimals(
        min_value=Decimal(min_value),
        max_value=Decimal(max_value),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    )


def topup_drafts(student_ids: list[int]) -> st.SearchStrategy[JournalEntryDraft]:
    """Draws balanced top-up JEs (Dr 1010 / Cr 2050) for random students."""
    return st.builds(
        _build_topup,
        amount=aed_amounts(min_value=1, max_value=10_000),
        student_id=st.sampled_from(student_ids),
        day=st.integers(min_value=1, max_value=28),
    )


def consume_drafts(
    student_ids: list[int],
    max_amount: Decimal,
) -> st.SearchStrategy[JournalEntryDraft]:
    """Wallet consumption JE (Dr 2050 / Cr 4010) capped by max_amount."""
    return st.builds(
        _build_consume,
        amount=st.decimals(
            min_value=Decimal("1.00"),
            max_value=max_amount,
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        student_id=st.sampled_from(student_ids),
        day=st.integers(min_value=1, max_value=28),
    )


def _build_topup(amount: Decimal, student_id: int, day: int) -> JournalEntryDraft:
    return JournalEntryDraft(
        date=date(2026, 4, day),
        narration=f"Hypothesis topup {amount}",
        source="manual:hypothesis",
        source_kind="manual",
        posted_by="hypothesis",
        lines=[
            JournalLineDraft(account_code="1010", debit_aed=amount),
            JournalLineDraft(
                account_code="2050",
                credit_aed=amount,
                sub_ledger_keys={"student_id": student_id},
            ),
        ],
    )


def _build_consume(amount: Decimal, student_id: int, day: int) -> JournalEntryDraft:
    return JournalEntryDraft(
        date=date(2026, 4, day),
        narration=f"Hypothesis consume {amount}",
        source="system:revenue_agent",
        source_kind="system",
        posted_by="hypothesis",
        lines=[
            JournalLineDraft(
                account_code="2050",
                debit_aed=amount,
                sub_ledger_keys={"student_id": student_id},
            ),
            JournalLineDraft(account_code="4010", credit_aed=amount),
        ],
    )


# ---------------------------------------------------------------------------
# DB-backed helpers
# ---------------------------------------------------------------------------


def trial_balance_zero(session: Session) -> bool:
    """Return True iff sum(debit_aed) == sum(credit_aed) across all lines."""
    from sqlalchemy import text

    row = session.execute(
        text(
            "SELECT COALESCE(SUM(debit_aed), 0) AS d, "
            "       COALESCE(SUM(credit_aed), 0) AS c "
            "FROM ledger.journal_lines",
        ),
    ).one()
    return row.d == row.c


@pytest.fixture
def some_students(db_session: Session) -> list[int]:
    """Five test students for property-based generators."""
    from sqlalchemy import text

    ids = []
    for i in range(5):
        sid = int(
            db_session.execute(
                text(
                    "INSERT INTO master.students (display_id, name) "
                    "VALUES (:d, :n) RETURNING student_id",
                ),
                {"d": f"PROP{i:03d}", "n": f"Property Student {i}"},
            ).scalar_one(),
        )
        ids.append(sid)
    return ids
