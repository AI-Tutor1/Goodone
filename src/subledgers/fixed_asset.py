"""Fixed-asset sub-ledger.

Per asset class (laptops, furniture, office equipment) the cost account is
debit-normal (1111/1113/1115) and the accumulated-depreciation contra is
credit-normal (1112/1114/1116). The Phase-2 reconciliation routine compares
the *net book value* (cost − accumulated depreciation) against the
sub-ledger sum.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from src.core.money import ZERO_AED, aed
from src.ledger.coa import SubLedgerName
from src.ledger.subledger import ReconciliationResult, signed_delta

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.ledger.posting import JournalLineDraft


_COST_ACCOUNTS = ("1111", "1113", "1115")
_ACCUM_ACCOUNTS = ("1112", "1114", "1116")
_ALL = _COST_ACCOUNTS + _ACCUM_ACCOUNTS


class FixedAssetSubLedger:
    name = SubLedgerName.FIXED_ASSET
    control_accounts = _ALL
    key_field = "asset_id"

    def apply_line(
        self,
        session: Session,
        *,
        je_id: int,
        line_id: int,
        period: str,
        effective_date: date,
        line: JournalLineDraft,
    ) -> None:
        # Phase-2 records depreciation entries; cost-side acquisitions land
        # via fixed_assets directly during seed. We only mirror to
        # fixed_asset_depreciation_entries when the line hits an accumulated
        # depreciation account.
        if line.account_code not in _ACCUM_ACCOUNTS:
            return
        asset_id = int(line.sub_ledger_keys["asset_id"])
        # Accum dep is credit-normal: a credit grows accumulated depreciation.
        delta = signed_delta(line, side="credit")
        if delta <= ZERO_AED:
            return  # ignore reversals here; period.py / reverse_journal handles those rows
        session.execute(
            text(
                """
                INSERT INTO assets.fixed_asset_depreciation_entries (
                    asset_id, je_id, line_id, period, monthly_amount_aed
                ) VALUES (
                    :asset_id, :je_id, :line_id, :period, :amount
                )
                """,
            ),
            {
                "asset_id": asset_id,
                "je_id": je_id,
                "line_id": line_id,
                "period": period,
                "amount": delta,
            },
        )

    def row_exists(self, session: Session, key: str | int) -> bool:
        return bool(
            session.execute(
                text(
                    "SELECT 1 FROM assets.fixed_assets WHERE asset_id = :id",
                ),
                {"id": int(key)},
            ).scalar(),
        )

    def balance(
        self,
        session: Session,
        key: str | int,
        *,
        as_of: date | None = None,
    ) -> Decimal:
        """Net book value for a single asset = cost − accumulated depreciation."""
        cost_row = session.execute(
            text(
                "SELECT cost_aed FROM assets.fixed_assets WHERE asset_id = :id",
            ),
            {"id": int(key)},
        ).one_or_none()
        if cost_row is None:
            return ZERO_AED
        accum = session.execute(
            text(
                "SELECT COALESCE(SUM(monthly_amount_aed), 0) "
                "FROM assets.fixed_asset_depreciation_entries "
                "WHERE asset_id = :id" + (" AND created_at::date <= :as_of" if as_of else ""),
            ),
            {"id": int(key), "as_of": as_of} if as_of else {"id": int(key)},
        ).scalar_one()
        return aed(cost_row.cost_aed) - aed(accum)

    def reconcile_to_gl(
        self,
        session: Session,
        *,
        as_of: date | None = None,
    ) -> ReconciliationResult:
        # GL net book value across the three classes.
        gl_cost = _debit_normal_balance(session, _COST_ACCOUNTS, as_of=as_of)
        gl_accum = _credit_normal_balance(session, _ACCUM_ACCOUNTS, as_of=as_of)
        gl_nbv = gl_cost - gl_accum

        sub_cost = aed(
            session.execute(
                text("SELECT COALESCE(SUM(cost_aed), 0) FROM assets.fixed_assets"),
            ).scalar_one(),
        )
        sub_accum = aed(
            session.execute(
                text(
                    "SELECT COALESCE(SUM(monthly_amount_aed), 0) "
                    "FROM assets.fixed_asset_depreciation_entries"
                    + (" WHERE created_at::date <= :as_of" if as_of else ""),
                ),
                {"as_of": as_of} if as_of else {},
            ).scalar_one(),
        )
        sub_nbv = sub_cost - sub_accum
        diff = gl_nbv - sub_nbv
        return ReconciliationResult(
            sub_ledger="fixed_asset",
            matches=(diff == ZERO_AED),
            gl_balance=gl_nbv,
            sub_ledger_sum=sub_nbv,
            diff=diff,
            per_key_diffs={},
        )


def _debit_normal_balance(
    session: Session,
    codes: tuple[str, ...],
    *,
    as_of: date | None,
) -> Decimal:
    sql = (
        "SELECT COALESCE(SUM(jl.debit_aed - jl.credit_aed), 0) "
        "FROM ledger.journal_lines jl "
        "JOIN ledger.journal_entries je ON je.je_id = jl.je_id "
        "WHERE jl.account_code = ANY(:codes) "
    )
    params: dict[str, object] = {"codes": list(codes)}
    if as_of is not None:
        sql += "AND je.date <= :as_of "
        params["as_of"] = as_of
    return aed(session.execute(text(sql), params).scalar_one())


def _credit_normal_balance(
    session: Session,
    codes: tuple[str, ...],
    *,
    as_of: date | None,
) -> Decimal:
    sql = (
        "SELECT COALESCE(SUM(jl.credit_aed - jl.debit_aed), 0) "
        "FROM ledger.journal_lines jl "
        "JOIN ledger.journal_entries je ON je.je_id = jl.je_id "
        "WHERE jl.account_code = ANY(:codes) "
    )
    params: dict[str, object] = {"codes": list(codes)}
    if as_of is not None:
        sql += "AND je.date <= :as_of "
        params["as_of"] = as_of
    return aed(session.execute(text(sql), params).scalar_one())
