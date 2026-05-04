"""initial schema (master / ledger / subledger / assets / sanctions / audit / staging)

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-04

This migration creates every table needed for the Phase 2 ledger engine. The
seven schemas themselves are created by ``infra/postgres/init.sql`` on the
container's first boot (and by the equivalent provisioning step on the VPS).

Design notes:

* All money columns are NUMERIC(18, 2) AED unless explicitly noted.
* FX rates are NUMERIC(18, 8). Original-currency amounts on sub-ledgers are
  NUMERIC(18, 4) (PKR can have larger magnitudes than AED).
* Two enforcement layers protect the GL invariants:
    1. Python validation in ``src/ledger/posting.py`` (clean errors).
    2. Postgres CHECK constraints + triggers (belt-and-braces).
  If they ever disagree on whether a row is acceptable, the DB wins.
* The wallet non-negative trigger is a row-level AFTER trigger that re-sums
  the affected student's entries and aborts the transaction on negative.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# Reusable enums (created at the schema level so downgrade can drop them).
# ---------------------------------------------------------------------------

# NOTE: SA emits each named enum exactly once, immediately before its first
# referencing column. We rely on that and do NOT call ``enum.create()`` in
# upgrade() — doing so produces duplicate ``CREATE TYPE`` statements in
# Alembic offline (``--sql``) output.


def _e(*values: str, name: str) -> sa.Enum:
    return sa.Enum(*values, name=name)


PERIOD_STATUS = _e("OPEN", "IN_CLOSING", "CLOSED", "REOPENED", name="period_status")
ACCOUNT_TYPE = _e(
    "asset",
    "liability",
    "equity",
    "revenue",
    "expense",
    "contra",
    "memo",
    name="account_type",
)
ACCOUNT_NORMAL_BALANCE = _e("debit", "credit", name="account_normal_balance")
ACCOUNT_STATEMENT = _e("BS", "IS", "MEMO", name="account_statement")
ACCOUNT_SUB_LEDGER = _e(
    "student_wallet",
    "tutor_payable",
    "fixed_asset",
    "prepaid",
    "intangible",
    "sanction_memo",
    name="account_sub_ledger",
)
ACCOUNT_CURRENCY = _e("AED", "PKR", name="account_currency")

JE_STATUS = _e("POSTED", "REVERSED", name="je_status")
JE_SOURCE_KIND = _e("system", "manual", "import", name="je_source_kind")

WALLET_ENTRY_TYPE = _e("TOPUP", "CONSUME", "REFUND", "ADJUST", name="wallet_entry_type")

PAYMENT_CURRENCY = _e("AED", "PKR", name="payment_currency")

ENROLLMENT_STATUS = _e("active", "paused", "churned", name="enrollment_status")

FIXED_ASSET_CLASS = _e("LAPTOP", "FURNITURE", "OFFICE_EQUIPMENT", name="fixed_asset_class")
FIXED_ASSET_STATUS = _e("ACTIVE", "DISPOSED", name="fixed_asset_status")

INTANGIBLE_STATUS = _e("IN_DEVELOPMENT", "LAUNCHED", name="intangible_status")
INTANGIBLE_ENTRY_TYPE = _e(
    "CAPITALIZE",
    "RECLASS_TO_LAUNCHED",
    "AMORTIZE",
    name="intangible_entry_type",
)

SANCTION_STATUS = _e(
    "DRAFT",
    "PENDING_FA",
    "PENDING_CFO",
    "APPROVED",
    "REJECTED",
    "CLOSED",
    name="sanction_status",
)
SANCTION_MEMO_SIDE = _e("COMMIT", "CONTRA", "SPEND_REVERSE", name="sanction_memo_side")

AUDIT_ACTION = _e(
    "POST_JOURNAL",
    "REVERSE_JOURNAL",
    "REJECT_JOURNAL",
    "OPEN_PERIOD",
    "BEGIN_CLOSING",
    "CLOSE_PERIOD",
    "REOPEN_PERIOD",
    "COA_LOAD",
    name="audit_action",
)

PERIOD_LOG_ACTION = _e("CLOSE", "REOPEN", name="period_log_action")

QUARANTINE_STATUS = _e("OPEN", "RESOLVED", "REJECTED", name="quarantine_status")


# ---------------------------------------------------------------------------
def upgrade() -> None:
    # SQLAlchemy emits each named enum exactly once before its first
    # referencing column — no explicit enum.create() loop needed, and that
    # keeps Alembic offline (``--sql``) output free of duplicate CREATE TYPEs.

    # =====================================================================
    # master schema
    # =====================================================================

    op.create_table(
        "chart_of_accounts",
        sa.Column("code", sa.String(4), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", ACCOUNT_TYPE, nullable=False),
        sa.Column("normal_balance", ACCOUNT_NORMAL_BALANCE, nullable=False),
        sa.Column(
            "parent_code",
            sa.String(4),
            sa.ForeignKey("master.chart_of_accounts.code"),
            nullable=True,
        ),
        sa.Column("statement", ACCOUNT_STATEMENT, nullable=False),
        sa.Column("is_postable", sa.Boolean(), nullable=False),
        sa.Column("sub_ledger", ACCOUNT_SUB_LEDGER, nullable=True),
        sa.Column("currency", ACCOUNT_CURRENCY, nullable=True),
        sa.Column("is_memo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("subtype", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("yaml_version", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.CheckConstraint(
            "code ~ '^[0-9]{4}$'",
            name="code_is_4_digit",
        ),
        schema="master",
    )

    op.create_table(
        "periods",
        sa.Column("period", sa.String(7), primary_key=True),  # 'YYYY-MM'
        sa.Column("status", PERIOD_STATUS, nullable=False, server_default=sa.text("'OPEN'")),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.Text(), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopened_by", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'",
            name="period_format_yyyy_mm",
        ),
        schema="master",
    )

    op.create_table(
        "students",
        sa.Column("student_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("display_id", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="master",
    )

    op.create_table(
        "tutors",
        sa.Column("tutor_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("display_id", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("payment_currency", PAYMENT_CURRENCY, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="master",
    )

    op.create_table(
        "enrollments",
        sa.Column("enrollment_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "student_id",
            sa.BigInteger(),
            sa.ForeignKey("master.students.student_id"),
            nullable=False,
        ),
        sa.Column(
            "tutor_id", sa.BigInteger(), sa.ForeignKey("master.tutors.tutor_id"), nullable=False
        ),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("grade", sa.Text(), nullable=False),
        sa.Column("curriculum", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", ENROLLMENT_STATUS, nullable=False, server_default=sa.text("'active'")),
        schema="master",
    )

    op.create_table(
        "tutor_hour_rates",
        sa.Column("rate_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "tutor_id", sa.BigInteger(), sa.ForeignKey("master.tutors.tutor_id"), nullable=False
        ),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("grade", sa.Text(), nullable=False),
        sa.Column("curriculum", sa.Text(), nullable=False),
        sa.Column("rate_aed", sa.Numeric(18, 2), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.CheckConstraint("rate_aed >= 0", name="rate_aed_nonneg"),
        schema="master",
    )

    op.create_table(
        "student_hour_rates",
        sa.Column("rate_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("grade", sa.Text(), nullable=False),
        sa.Column("curriculum", sa.Text(), nullable=False),
        sa.Column("rate_aed", sa.Numeric(18, 2), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.CheckConstraint("rate_aed >= 0", name="rate_aed_nonneg"),
        schema="master",
    )

    op.create_table(
        "fx_rates",
        sa.Column("rate_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("base", sa.String(3), nullable=False),
        sa.Column("quote", sa.String(3), nullable=False),
        sa.Column("rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("rate > 0", name="rate_positive"),
        sa.UniqueConstraint(
            "date", "base", "quote", "source", name="uq_fx_rates_date_base_quote_source"
        ),
        schema="master",
    )

    # =====================================================================
    # ledger schema
    # =====================================================================

    op.create_table(
        "journal_entries",
        sa.Column("je_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("period", sa.String(7), sa.ForeignKey("master.periods.period"), nullable=False),
        sa.Column("narration", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_kind", JE_SOURCE_KIND, nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("source_version", sa.Text(), nullable=True),
        sa.Column("posted_by", sa.Text(), nullable=False),
        sa.Column(
            "posted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("total_debit_aed", sa.Numeric(18, 2), nullable=False),
        sa.Column("total_credit_aed", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "attachment_required", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("attachment_url", sa.Text(), nullable=True),
        sa.Column("attachment_override_reason", sa.Text(), nullable=True),
        sa.Column(
            "reverses_je_id",
            sa.BigInteger(),
            sa.ForeignKey("ledger.journal_entries.je_id"),
            nullable=True,
        ),
        sa.Column("status", JE_STATUS, nullable=False, server_default=sa.text("'POSTED'")),
        sa.CheckConstraint(
            "char_length(narration) >= 10",
            name="narration_min_length",
        ),
        sa.CheckConstraint(
            "total_debit_aed = total_credit_aed",
            name="dr_equals_cr",
        ),
        sa.CheckConstraint(
            "total_debit_aed >= 0",
            name="totals_nonneg",
        ),
        sa.CheckConstraint(
            "(NOT attachment_required) OR (attachment_url IS NOT NULL) "
            "OR (attachment_override_reason IS NOT NULL "
            "    AND char_length(attachment_override_reason) >= 30)",
            name="attachment_policy",
        ),
        schema="ledger",
    )
    op.create_index(
        "ix_journal_entries_period",
        "journal_entries",
        ["period"],
        schema="ledger",
    )

    op.create_table(
        "journal_lines",
        sa.Column("line_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "je_id",
            sa.BigInteger(),
            sa.ForeignKey("ledger.journal_entries.je_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "account_code",
            sa.String(4),
            sa.ForeignKey("master.chart_of_accounts.code"),
            nullable=False,
        ),
        sa.Column("debit_aed", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("credit_aed", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "sub_ledger_keys",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "dimensions",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("original_currency", sa.String(3), nullable=True),
        sa.Column("original_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("fx_rate", sa.Numeric(18, 8), nullable=True),
        sa.CheckConstraint(
            "(debit_aed > 0 AND credit_aed = 0) OR (credit_aed > 0 AND debit_aed = 0)",
            name="debit_xor_credit",
        ),
        sa.CheckConstraint("debit_aed >= 0 AND credit_aed >= 0", name="amounts_nonneg"),
        schema="ledger",
    )
    op.create_index(
        "ix_journal_lines_account_code",
        "journal_lines",
        ["account_code"],
        schema="ledger",
    )
    op.create_index(
        "ix_journal_lines_je_id",
        "journal_lines",
        ["je_id"],
        schema="ledger",
    )
    op.execute(
        "CREATE INDEX ix_journal_lines_sub_ledger_keys "
        "ON ledger.journal_lines USING GIN (sub_ledger_keys);"
    )
    op.execute(
        "CREATE INDEX ix_journal_lines_dimensions ON ledger.journal_lines USING GIN (dimensions);"
    )

    # =====================================================================
    # subledger schema
    # =====================================================================

    op.create_table(
        "student_wallet_entries",
        sa.Column("entry_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "student_id",
            sa.BigInteger(),
            sa.ForeignKey("master.students.student_id"),
            nullable=False,
        ),
        sa.Column(
            "je_id", sa.BigInteger(), sa.ForeignKey("ledger.journal_entries.je_id"), nullable=False
        ),
        sa.Column(
            "line_id",
            sa.BigInteger(),
            sa.ForeignKey("ledger.journal_lines.line_id"),
            nullable=False,
        ),
        sa.Column("period", sa.String(7), sa.ForeignKey("master.periods.period"), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("delta_aed", sa.Numeric(18, 2), nullable=False),
        sa.Column("type", WALLET_ENTRY_TYPE, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="subledger",
    )
    op.create_index(
        "ix_student_wallet_entries_student_id",
        "student_wallet_entries",
        ["student_id"],
        schema="subledger",
    )

    # AFTER trigger guarding wallet non-negativity per accounting_rules.md §2.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION subledger.tg_check_wallet_nonneg()
        RETURNS TRIGGER AS $$
        DECLARE
            new_balance numeric(18, 2);
        BEGIN
            SELECT COALESCE(SUM(delta_aed), 0)
              INTO new_balance
              FROM subledger.student_wallet_entries
             WHERE student_id = NEW.student_id;
            IF new_balance < 0 THEN
                RAISE EXCEPTION
                    'student_wallet balance for student_id=% would go negative (%.2f)',
                    NEW.student_id, new_balance
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER tg_check_wallet_nonneg
        AFTER INSERT ON subledger.student_wallet_entries
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION subledger.tg_check_wallet_nonneg();
        """
    )

    op.create_table(
        "tutor_payable_entries",
        sa.Column("entry_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "tutor_id", sa.BigInteger(), sa.ForeignKey("master.tutors.tutor_id"), nullable=False
        ),
        sa.Column(
            "je_id", sa.BigInteger(), sa.ForeignKey("ledger.journal_entries.je_id"), nullable=False
        ),
        sa.Column(
            "line_id",
            sa.BigInteger(),
            sa.ForeignKey("ledger.journal_lines.line_id"),
            nullable=False,
        ),
        sa.Column("period", sa.String(7), sa.ForeignKey("master.periods.period"), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("delta_aed", sa.Numeric(18, 2), nullable=False),
        sa.Column("original_currency", sa.String(3), nullable=False),
        sa.Column("original_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("fx_rate_at_accrual", sa.Numeric(18, 8), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="subledger",
    )
    op.create_index(
        "ix_tutor_payable_entries_tutor_id",
        "tutor_payable_entries",
        ["tutor_id"],
        schema="subledger",
    )

    # =====================================================================
    # sanctions schema (minimal Phase-2 stub — workflow lives in Phase 4)
    # Created before subledger.sanction_memo_entries so the FK target exists.
    # =====================================================================

    op.create_table(
        "sanction_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("department", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("amount_aed", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", SANCTION_STATUS, nullable=False, server_default=sa.text("'DRAFT'")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.CheckConstraint("amount_aed > 0", name="amount_positive"),
        schema="sanctions",
    )

    op.create_table(
        "sanction_memo_entries",
        sa.Column("entry_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "sanction_request_id",
            sa.BigInteger(),
            sa.ForeignKey("sanctions.sanction_requests.id"),
            nullable=False,
        ),
        sa.Column(
            "je_id", sa.BigInteger(), sa.ForeignKey("ledger.journal_entries.je_id"), nullable=False
        ),
        sa.Column(
            "line_id",
            sa.BigInteger(),
            sa.ForeignKey("ledger.journal_lines.line_id"),
            nullable=False,
        ),
        sa.Column("period", sa.String(7), sa.ForeignKey("master.periods.period"), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("side", SANCTION_MEMO_SIDE, nullable=False),
        sa.Column("delta_aed", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="subledger",
    )

    # =====================================================================
    # assets schema
    # =====================================================================

    op.create_table(
        "fixed_assets",
        sa.Column("asset_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("asset_class", FIXED_ASSET_CLASS, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("cost_aed", sa.Numeric(18, 2), nullable=False),
        sa.Column("useful_life_months", sa.Integer(), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("in_service_date", sa.Date(), nullable=False),
        sa.Column("disposed_date", sa.Date(), nullable=True),
        sa.Column("status", FIXED_ASSET_STATUS, nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.CheckConstraint("cost_aed >= 0", name="cost_nonneg"),
        sa.CheckConstraint("useful_life_months > 0", name="life_positive"),
        schema="assets",
    )

    op.create_table(
        "fixed_asset_depreciation_entries",
        sa.Column("entry_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "asset_id",
            sa.BigInteger(),
            sa.ForeignKey("assets.fixed_assets.asset_id"),
            nullable=False,
        ),
        sa.Column(
            "je_id", sa.BigInteger(), sa.ForeignKey("ledger.journal_entries.je_id"), nullable=False
        ),
        sa.Column(
            "line_id",
            sa.BigInteger(),
            sa.ForeignKey("ledger.journal_lines.line_id"),
            nullable=False,
        ),
        sa.Column("period", sa.String(7), sa.ForeignKey("master.periods.period"), nullable=False),
        sa.Column("monthly_amount_aed", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="assets",
    )

    op.create_table(
        "prepaids",
        sa.Column("prepaid_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "account_code",
            sa.String(4),
            sa.ForeignKey("master.chart_of_accounts.code"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("total_aed", sa.Numeric(18, 2), nullable=False),
        sa.Column("total_months", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.CheckConstraint("total_aed >= 0", name="total_nonneg"),
        sa.CheckConstraint("total_months > 0", name="months_positive"),
        schema="assets",
    )

    op.create_table(
        "prepaid_amortization_entries",
        sa.Column("entry_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "prepaid_id",
            sa.BigInteger(),
            sa.ForeignKey("assets.prepaids.prepaid_id"),
            nullable=False,
        ),
        sa.Column(
            "je_id", sa.BigInteger(), sa.ForeignKey("ledger.journal_entries.je_id"), nullable=False
        ),
        sa.Column(
            "line_id",
            sa.BigInteger(),
            sa.ForeignKey("ledger.journal_lines.line_id"),
            nullable=False,
        ),
        sa.Column("period", sa.String(7), sa.ForeignKey("master.periods.period"), nullable=False),
        sa.Column("monthly_amount_aed", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="assets",
    )

    op.create_table(
        "intangibles",
        sa.Column("intangible_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "account_code",
            sa.String(4),
            sa.ForeignKey("master.chart_of_accounts.code"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", INTANGIBLE_STATUS, nullable=False),
        sa.Column("feasibility_date", sa.Date(), nullable=False),
        sa.Column("launch_date", sa.Date(), nullable=True),
        sa.Column("monthly_capitalization_aed", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "useful_life_months_post_launch",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("60"),
        ),
        schema="assets",
    )

    op.create_table(
        "intangible_entries",
        sa.Column("entry_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "intangible_id",
            sa.BigInteger(),
            sa.ForeignKey("assets.intangibles.intangible_id"),
            nullable=False,
        ),
        sa.Column(
            "je_id", sa.BigInteger(), sa.ForeignKey("ledger.journal_entries.je_id"), nullable=False
        ),
        sa.Column(
            "line_id",
            sa.BigInteger(),
            sa.ForeignKey("ledger.journal_lines.line_id"),
            nullable=False,
        ),
        sa.Column("period", sa.String(7), sa.ForeignKey("master.periods.period"), nullable=False),
        sa.Column("type", INTANGIBLE_ENTRY_TYPE, nullable=False),
        sa.Column("delta_aed", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        schema="assets",
    )

    # =====================================================================
    # audit schema
    # =====================================================================

    op.create_table(
        "audit_log",
        sa.Column("log_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("action", AUDIT_ACTION, nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column("before_state", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("after_state", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("tag", sa.Text(), nullable=True),
        schema="audit",
    )

    op.create_table(
        "period_close_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("period", sa.String(7), sa.ForeignKey("master.periods.period"), nullable=False),
        sa.Column("action", PERIOD_LOG_ACTION, nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("gl_balances_snapshot", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("sub_ledger_balances_snapshot", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("summary_metrics", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.CheckConstraint(
            "action <> 'REOPEN' OR (reason IS NOT NULL AND char_length(reason) >= 30)",
            name="reopen_reason_required",
        ),
        schema="audit",
    )

    # =====================================================================
    # staging schema
    # =====================================================================

    op.create_table(
        "data_quality_quarantine",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("batch_id", sa.Text(), nullable=False),
        sa.Column("raw_payload", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("validation_errors", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("status", QUARANTINE_STATUS, nullable=False, server_default=sa.text("'OPEN'")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Text(), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("affected_period", sa.String(7), nullable=True),
        schema="staging",
    )


# ---------------------------------------------------------------------------
def downgrade() -> None:
    # Drop tables in reverse FK order. Enums are dropped explicitly at the end.
    op.drop_table("data_quality_quarantine", schema="staging")
    op.drop_table("period_close_log", schema="audit")
    op.drop_table("audit_log", schema="audit")

    op.drop_table("intangible_entries", schema="assets")
    op.drop_table("intangibles", schema="assets")
    op.drop_table("prepaid_amortization_entries", schema="assets")
    op.drop_table("prepaids", schema="assets")
    op.drop_table("fixed_asset_depreciation_entries", schema="assets")
    op.drop_table("fixed_assets", schema="assets")

    op.drop_table("sanction_memo_entries", schema="subledger")
    op.drop_table("tutor_payable_entries", schema="subledger")

    op.execute("DROP TRIGGER IF EXISTS tg_check_wallet_nonneg ON subledger.student_wallet_entries;")
    op.execute("DROP FUNCTION IF EXISTS subledger.tg_check_wallet_nonneg();")
    op.drop_table("student_wallet_entries", schema="subledger")

    op.drop_table("sanction_requests", schema="sanctions")

    op.drop_index("ix_journal_lines_dimensions", table_name="journal_lines", schema="ledger")
    op.drop_index("ix_journal_lines_sub_ledger_keys", table_name="journal_lines", schema="ledger")
    op.drop_table("journal_lines", schema="ledger")
    op.drop_table("journal_entries", schema="ledger")

    op.drop_table("fx_rates", schema="master")
    op.drop_table("student_hour_rates", schema="master")
    op.drop_table("tutor_hour_rates", schema="master")
    op.drop_table("enrollments", schema="master")
    op.drop_table("tutors", schema="master")
    op.drop_table("students", schema="master")
    op.drop_table("periods", schema="master")
    op.drop_table("chart_of_accounts", schema="master")

    bind = op.get_bind()
    for enum in (
        QUARANTINE_STATUS,
        PERIOD_LOG_ACTION,
        AUDIT_ACTION,
        SANCTION_MEMO_SIDE,
        SANCTION_STATUS,
        INTANGIBLE_ENTRY_TYPE,
        INTANGIBLE_STATUS,
        FIXED_ASSET_STATUS,
        FIXED_ASSET_CLASS,
        ENROLLMENT_STATUS,
        PAYMENT_CURRENCY,
        WALLET_ENTRY_TYPE,
        JE_SOURCE_KIND,
        JE_STATUS,
        ACCOUNT_CURRENCY,
        ACCOUNT_SUB_LEDGER,
        ACCOUNT_STATEMENT,
        ACCOUNT_NORMAL_BALANCE,
        ACCOUNT_TYPE,
        PERIOD_STATUS,
    ):
        enum.drop(bind, checkfirst=True)
