"""COA ↔ database synchronisation.

Reads ``docs/chart_of_accounts.yaml`` (via :class:`src.ledger.coa.COA`) and
upserts every account row into ``master.chart_of_accounts``. Idempotent: a
second invocation with the same YAML produces zero net writes (verified by
``tests/ledger/test_coa.py``).

The loader does **not** delete accounts that have disappeared from the YAML
(per ``docs/chart_of_accounts.md`` §"How to change the COA"). Removal requires
a deliberate migration step that first verifies no journal lines reference the
account; we'll add that helper in Phase 3 when ingestion + journals exist.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.core.config import get_settings
from src.ledger.coa import COA, set_active_coa

_UPSERT_SQL = text(
    """
    INSERT INTO master.chart_of_accounts (
        code, name, type, normal_balance, parent_code, statement,
        is_postable, sub_ledger, currency, is_memo, subtype, description,
        active, yaml_version, effective_from
    ) VALUES (
        :code, :name, :type, :normal_balance, :parent_code, :statement,
        :is_postable, :sub_ledger, :currency, :is_memo, :subtype, :description,
        true, :yaml_version, :effective_from
    )
    ON CONFLICT (code) DO UPDATE SET
        name           = EXCLUDED.name,
        type           = EXCLUDED.type,
        normal_balance = EXCLUDED.normal_balance,
        parent_code    = EXCLUDED.parent_code,
        statement      = EXCLUDED.statement,
        is_postable    = EXCLUDED.is_postable,
        sub_ledger     = EXCLUDED.sub_ledger,
        currency       = EXCLUDED.currency,
        is_memo        = EXCLUDED.is_memo,
        subtype        = EXCLUDED.subtype,
        description    = EXCLUDED.description,
        yaml_version   = EXCLUDED.yaml_version,
        effective_from = EXCLUDED.effective_from
    """,
)


def load_into_db(connection: Connection, *, yaml_path: Path | None = None) -> int:
    """Load the YAML into ``master.chart_of_accounts``.

    Returns the number of accounts written. Sets the process-wide active COA
    as a side effect so subsequent code can call :func:`get_active_coa`.
    """
    settings = get_settings()
    path = yaml_path or settings.coa_path
    coa = COA.load_from_yaml(path)

    # Two-pass write: parents first, then children — avoids transient FK
    # violation when a child is inserted before its parent (the parent FK
    # references master.chart_of_accounts(code), which is itself the table
    # we're inserting into).
    parents = [a for a in coa.all_active() if a.parent is None]
    children = [a for a in coa.all_active() if a.parent is not None]

    written = 0
    for batch in (parents, children):
        for acct in batch:
            connection.execute(
                _UPSERT_SQL,
                {
                    "code": acct.code,
                    "name": acct.name,
                    "type": acct.type.value,
                    "normal_balance": acct.normal_balance.value,
                    "parent_code": acct.parent,
                    "statement": acct.statement.value,
                    "is_postable": acct.is_postable,
                    "sub_ledger": acct.sub_ledger.value if acct.sub_ledger else None,
                    "currency": acct.currency,
                    "is_memo": acct.is_memo,
                    "subtype": acct.subtype,
                    "description": acct.description,
                    "yaml_version": coa.version,
                    "effective_from": _parse_date(coa.effective_from),
                },
            )
            written += 1

    set_active_coa(coa)
    return written


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)
