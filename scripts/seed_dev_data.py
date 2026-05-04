"""Seed the dev DB with the Phase-2 partial smoketest fixture.

Run via ``make seed-dev`` (or ``uv run python -m scripts.seed_dev_data``).

Loads, in order, against an already-migrated DB:

1. Chart of accounts (idempotent upsert).
2. Period ``2026-04`` (OPEN).
3. Five test students + two test tutors.
4. Opening balances JE (Cash AED + Share Capital + a few wallet balances).
5. Five wallet top-ups across three students.
6. Two wallet refunds.
7. Twenty conducted-session JEs (revenue + tutor accrual). The canonical
   46-min/60-min/AED-2500 penalty case lands as the last session so the
   golden file can spot-check it by ``source_ref='SES-PENALTY'``.

Phase-2 close is *not* invoked here — the smoketest test does that.
"""

from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from src.core.db import get_engine
from src.ledger.coa_loader import load_into_db
from src.ledger.posting import JournalEntryDraft, JournalLineDraft, post_journal
from src.ledger.subledger import build_default_registry

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection


PERIOD = "2026-04"


def seed(connection: Connection, *, fast: bool = False) -> dict[str, object]:
    """Run the full seed flow against *connection*. Returns a small summary."""
    load_into_db(connection)
    _ensure_period(connection)
    students, tutors = _ensure_master_data(connection)

    from src.ledger.coa import get_active_coa

    coa = get_active_coa()
    registry = build_default_registry()

    # Wrap the engine session so post_journal works against the connection.
    from sqlalchemy.orm import Session

    with Session(bind=connection) as session:
        _post_opening_balances(session, coa, registry, students)

        topup_count = _post_topups(session, coa, registry, students)
        refund_count = _post_refunds(session, coa, registry, students)

        if not fast:
            session_count = _post_sessions(session, coa, registry, students, tutors)
        else:
            session_count = 0

        session.flush()

    return {
        "students": len(students),
        "tutors": len(tutors),
        "topups": topup_count,
        "refunds": refund_count,
        "sessions": session_count,
    }


# ---------------------------------------------------------------------------


def _ensure_period(connection: Connection) -> None:
    connection.execute(
        text(
            "INSERT INTO master.periods (period, status, opened_at) "
            "VALUES (:p, 'OPEN', NOW()) ON CONFLICT DO NOTHING",
        ),
        {"p": PERIOD},
    )
    # Also seed March 2026 so the smoketest can post pre-opening balances if
    # the test author wants.
    connection.execute(
        text(
            "INSERT INTO master.periods (period, status, opened_at) "
            "VALUES ('2026-03', 'CLOSED', NOW()) ON CONFLICT DO NOTHING",
        ),
    )


def _ensure_master_data(
    connection: Connection,
) -> tuple[list[int], list[int]]:
    student_ids: list[int] = []
    for i in range(1, 6):
        sid = connection.execute(
            text(
                "INSERT INTO master.students (display_id, name) "
                "VALUES (:d, :n) ON CONFLICT (display_id) DO UPDATE "
                "SET name = EXCLUDED.name RETURNING student_id",
            ),
            {"d": f"S{i:03d}", "n": f"Smoketest Student {i}"},
        ).scalar_one()
        student_ids.append(int(sid))

    tutor_ids: list[int] = []
    for i, currency in enumerate([("T01", "PKR"), ("T02", "PKR"), ("T03", "AED")], start=1):
        tid = connection.execute(
            text(
                "INSERT INTO master.tutors (display_id, name, payment_currency) "
                "VALUES (:d, :n, :c) ON CONFLICT (display_id) DO UPDATE "
                "SET name = EXCLUDED.name RETURNING tutor_id",
            ),
            {"d": currency[0], "n": f"Smoketest Tutor {i}", "c": currency[1]},
        ).scalar_one()
        tutor_ids.append(int(tid))

    return student_ids, tutor_ids


def _post_opening_balances(session, coa, registry, students: list[int]) -> None:
    # Drop in opening cash + share capital + a couple of wallet seed balances.
    post_journal(
        session,
        JournalEntryDraft(
            date=date(2026, 4, 1),
            narration="Phase-2 seed: opening balances",
            source="import:seed_dev_data",
            source_kind="import",
            source_ref="OPEN-2026-04",
            posted_by="seed",
            lines=[
                JournalLineDraft(account_code="1010", debit_aed=Decimal("250000.00")),
                JournalLineDraft(account_code="3010", credit_aed=Decimal("100000.00")),
                JournalLineDraft(account_code="3020", credit_aed=Decimal("100000.00")),
                JournalLineDraft(
                    account_code="2050",
                    credit_aed=Decimal("30000.00"),
                    sub_ledger_keys={"student_id": students[0]},
                ),
                JournalLineDraft(
                    account_code="2050",
                    credit_aed=Decimal("20000.00"),
                    sub_ledger_keys={"student_id": students[1]},
                ),
            ],
        ),
        coa=coa,
        sub_ledgers=registry,
    )


def _post_topups(session, coa, registry, students: list[int]) -> int:
    topups: list[tuple[int, str, str]] = [
        (students[0], "1500.00", "2026-04-02"),
        (students[1], "2500.00", "2026-04-04"),
        (students[2], "3000.00", "2026-04-06"),
        (students[2], "1000.00", "2026-04-09"),
        (students[3], "2000.00", "2026-04-12"),
    ]
    for sid, amount, d in topups:
        y, m, day = (int(x) for x in d.split("-"))
        post_journal(
            session,
            JournalEntryDraft(
                date=date(y, m, day),
                narration=f"Wallet top-up student {sid} on {d}",
                source="import:seed_dev_data",
                source_kind="import",
                source_ref=f"TOPUP-{sid}-{d}",
                posted_by="seed",
                lines=[
                    JournalLineDraft(account_code="1010", debit_aed=Decimal(amount)),
                    JournalLineDraft(
                        account_code="2050",
                        credit_aed=Decimal(amount),
                        sub_ledger_keys={"student_id": sid},
                    ),
                ],
            ),
            coa=coa,
            sub_ledgers=registry,
        )
    return len(topups)


def _post_refunds(session, coa, registry, students: list[int]) -> int:
    refunds: list[tuple[int, str, str]] = [
        (students[0], "200.00", "2026-04-08"),
        (students[3], "500.00", "2026-04-15"),
    ]
    for sid, amount, d in refunds:
        y, m, day = (int(x) for x in d.split("-"))
        post_journal(
            session,
            JournalEntryDraft(
                date=date(y, m, day),
                narration=f"Wallet refund student {sid} on {d}",
                source="import:seed_dev_data",
                source_kind="import",
                source_ref=f"REFUND-{sid}-{d}",
                posted_by="seed",
                lines=[
                    JournalLineDraft(
                        account_code="2050",
                        debit_aed=Decimal(amount),
                        sub_ledger_keys={"student_id": sid},
                    ),
                    JournalLineDraft(account_code="1010", credit_aed=Decimal(amount)),
                ],
            ),
            coa=coa,
            sub_ledgers=registry,
        )
    return len(refunds)


def _post_sessions(
    session, coa, registry, students: list[int], tutors: list[int],
) -> int:
    """Post 20 conducted sessions: 19 simple + 1 canonical-penalty.

    Each conducted session ≥ 52 min: revenue ``Dr 2050 / Cr 4010`` and
    tutor accrual ``Dr 5010 / Cr 2020``. The penalty case posts the
    revised three-line cost JE per accounting_rules.md §4.
    """
    count = 0
    rate_aed = Decimal("100.00")  # student hourly
    tutor_rate = Decimal("80.00")  # tutor hourly
    for i in range(19):
        # Cycle through students 0..3 only — student[4] is left empty so the
        # smoketest can demonstrate the wallet-non-negative rule against it
        # in a manual ad-hoc test if desired.
        student_id = students[i % 4]
        tutor_id = tutors[i % 2]  # only PKR tutors here for smoketest
        d = date(2026, 4, 10 + (i % 15))
        # Revenue
        post_journal(
            session,
            JournalEntryDraft(
                date=d,
                narration=f"Session {i:03d} revenue (conducted >= 52)",
                source="system:revenue_agent",
                source_kind="system",
                source_ref=f"SES-{i:03d}-REV",
                posted_by="seed",
                lines=[
                    JournalLineDraft(
                        account_code="2050",
                        debit_aed=rate_aed,
                        sub_ledger_keys={"student_id": student_id},
                    ),
                    JournalLineDraft(account_code="4010", credit_aed=rate_aed),
                ],
            ),
            coa=coa,
            sub_ledgers=registry,
        )
        # Tutor accrual
        post_journal(
            session,
            JournalEntryDraft(
                date=d,
                narration=f"Session {i:03d} tutor accrual (conducted >= 52)",
                source="system:payroll_agent",
                source_kind="system",
                source_ref=f"SES-{i:03d}-COST",
                posted_by="seed",
                lines=[
                    JournalLineDraft(account_code="5010", debit_aed=tutor_rate),
                    JournalLineDraft(
                        account_code="2020",
                        credit_aed=tutor_rate,
                        sub_ledger_keys={"tutor_id": tutor_id},
                        original_currency="PKR",
                        original_amount=Decimal("6040.00"),  # ~ 80 AED * 75.5
                        fx_rate=Decimal("75.50000000"),
                    ),
                ],
            ),
            coa=coa,
            sub_ledgers=registry,
        )
        count += 2

    # Canonical penalty case: 46/60 × 2500 × 0.95.
    student_id = students[0]
    tutor_id = tutors[0]
    rate = Decimal("2500.00")
    prorated = rate * Decimal("46") / Decimal("60")  # 1916.666...
    prorated_q = prorated.quantize(Decimal("0.01"))
    net_pay = (prorated * Decimal("0.95")).quantize(Decimal("0.01"))
    penalty = (prorated_q - net_pay).quantize(Decimal("0.01"))

    # Revenue (student is billed for the FULL scheduled session)
    post_journal(
        session,
        JournalEntryDraft(
            date=date(2026, 4, 25),
            narration="Session PENALTY revenue (canonical 46/60/2500)",
            source="system:revenue_agent",
            source_kind="system",
            source_ref="SES-PENALTY-REV",
            posted_by="seed",
            lines=[
                JournalLineDraft(
                    account_code="2050",
                    debit_aed=rate,
                    sub_ledger_keys={"student_id": student_id},
                ),
                JournalLineDraft(account_code="4010", credit_aed=rate),
            ],
        ),
        coa=coa,
        sub_ledgers=registry,
    )
    # Cost — three-line balanced (5010 prorated; 2020 net_pay; 5020 penalty)
    post_journal(
        session,
        JournalEntryDraft(
            date=date(2026, 4, 25),
            narration="Session PENALTY tutor accrual with penalty contra",
            source="system:payroll_agent",
            source_kind="system",
            source_ref="SES-PENALTY-COST",
            posted_by="seed",
            lines=[
                JournalLineDraft(account_code="5010", debit_aed=prorated_q),
                JournalLineDraft(
                    account_code="2020",
                    credit_aed=net_pay,
                    sub_ledger_keys={"tutor_id": tutor_id},
                    original_currency="PKR",
                    original_amount=net_pay * Decimal("75.50"),
                    fx_rate=Decimal("75.50000000"),
                ),
                JournalLineDraft(account_code="5020", credit_aed=penalty),
            ],
        ),
        coa=coa,
        sub_ledgers=registry,
    )
    count += 2
    return count


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Seed Phase-2 dev/smoketest data")
    parser.add_argument("--fast", action="store_true",
                        help="skip the 20 session JEs (top-ups + refunds only)")
    args = parser.parse_args(argv)

    engine = get_engine()
    with engine.begin() as conn:
        summary = seed(conn, fast=args.fast)
        print("seed complete:", summary)


if __name__ == "__main__":  # pragma: no cover
    main()
