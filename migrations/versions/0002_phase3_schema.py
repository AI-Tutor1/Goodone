"""Phase 3 schema additions.

Revision ID: 0002_phase3_schema
Revises: 0001_initial
Create Date: 2026-05-05

Adds:
  1. Partial unique index on ledger.journal_entries(source_ref) — idempotency guard
  2. master.sessions — persists LMS session records for reporting + productivity reports
  3. audit.chat_sessions + audit.chat_messages — Postgres-backed chat persistence
  4. staging.attachments — file upload registry (replaces free-text attachment_url)
  5. staging.manual_uploads — batch upload job tracker
  6. subledger.tutor_disbursements — payout disbursement records
  7. master.budget_entries — budget vs. actual module
  8. staging.lms_sync_log — LMS polling run history
  9. New audit_action enum values: UPLOAD_SESSIONS, DISBURSE_PAYROLL, BUDGET_POST, LOGIN_TOTP

Note: master.tutor_hour_rates (rate versioning) already exists from 0001_initial.
Note: staging.data_quality_quarantine already exists from 0001_initial.
Note: master.fx_rates.source column already exists from 0001_initial.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase3_schema"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SESSION_STATUS = sa.Enum(
    "conducted",
    "student_absent",
    "teacher_absent",
    "cancelled",
    "no_show",
    name="session_status",
)

DISBURSEMENT_CURRENCY = sa.Enum("AED", "PKR", name="disbursement_currency")

UPLOAD_SOURCE_KIND = sa.Enum(
    "sessions",
    "enrollments",
    "payroll",
    "bank_statement",
    name="upload_source_kind",
)

UPLOAD_STATUS = sa.Enum(
    "processing",
    "done",
    "failed",
    name="upload_status",
)


def upgrade() -> None:
    # =========================================================================
    # 1. Idempotency index on ledger.journal_entries(source_ref)
    #
    # Partial index (WHERE source_ref IS NOT NULL) so that JEs without a
    # source_ref (manual entries, opening balances) are never caught by the
    # uniqueness constraint. Standard PostgreSQL UNIQUE also allows multiple
    # NULLs, but a partial index is cleaner and more explicit.
    # =========================================================================
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_uq_je_source_ref
        ON ledger.journal_entries (source_ref)
        WHERE source_ref IS NOT NULL
        """
    )

    # =========================================================================
    # 2. master.sessions — persists every session pulled from the LMS.
    #    Needed by the tutor productivity report (B19) and for the ingestion
    #    pipeline to detect duplicates without scanning journal_entries.
    # =========================================================================
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.Text(), primary_key=True),
        sa.Column(
            "enrollment_id",
            sa.BigInteger(),
            sa.ForeignKey("master.enrollments.enrollment_id"),
            nullable=False,
        ),
        sa.Column("scheduled_minutes", sa.Integer(), nullable=False),
        sa.Column("conducted_minutes", sa.Integer(), nullable=False),
        sa.Column("status", SESSION_STATUS, nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("period", sa.String(7), sa.ForeignKey("master.periods.period"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("revenue_je_id", sa.BigInteger(), nullable=True),
        sa.Column("payroll_je_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint("scheduled_minutes > 0", name="sessions_scheduled_pos"),
        sa.CheckConstraint("conducted_minutes >= 0", name="sessions_conducted_nonneg"),
        schema="master",
    )
    op.create_index(
        "ix_sessions_enrollment_id",
        "sessions",
        ["enrollment_id"],
        schema="master",
    )
    op.create_index(
        "ix_sessions_occurred_on",
        "sessions",
        ["occurred_on"],
        schema="master",
    )

    # =========================================================================
    # 3. Postgres-backed chat persistence
    # =========================================================================
    op.create_table(
        "chat_sessions",
        sa.Column("session_id", sa.String(12), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("user_id", sa.Text(), nullable=False),
        schema="audit",
    )

    op.create_table(
        "chat_messages",
        sa.Column("msg_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.String(12),
            sa.ForeignKey("audit.chat_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=True),
        sa.Column(
            "tool_input",
            sa.dialects.postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'tool')",
            name="chat_messages_role_valid",
        ),
        schema="audit",
    )
    op.create_index(
        "ix_chat_messages_session_id",
        "chat_messages",
        ["session_id", "msg_id"],
        schema="audit",
    )

    # =========================================================================
    # 4. staging.attachments — file upload registry
    # =========================================================================
    op.create_table(
        "attachments",
        sa.Column("attachment_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("stored_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.Text(), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "linked_je_id",
            sa.BigInteger(),
            sa.ForeignKey("ledger.journal_entries.je_id"),
            nullable=True,
        ),
        sa.CheckConstraint("size_bytes > 0", name="attachment_size_pos"),
        schema="staging",
    )

    # =========================================================================
    # 5. staging.manual_uploads — batch upload job tracker
    # =========================================================================
    op.create_table(
        "manual_uploads",
        sa.Column("upload_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.Text(), nullable=False, unique=True),
        sa.Column("source_kind", UPLOAD_SOURCE_KIND, nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("accepted", sa.Integer(), nullable=True),
        sa.Column("skipped", sa.Integer(), nullable=True),
        sa.Column("quarantined", sa.Integer(), nullable=True),
        sa.Column("uploaded_by", sa.Text(), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("status", UPLOAD_STATUS, nullable=False, server_default=sa.text("'processing'")),
        sa.Column("error_message", sa.Text(), nullable=True),
        schema="staging",
    )

    # =========================================================================
    # 6. subledger.tutor_disbursements — actual payout records
    # =========================================================================
    op.create_table(
        "tutor_disbursements",
        sa.Column("disbursement_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "tutor_id",
            sa.BigInteger(),
            sa.ForeignKey("master.tutors.tutor_id"),
            nullable=False,
        ),
        sa.Column(
            "je_id",
            sa.BigInteger(),
            sa.ForeignKey("ledger.journal_entries.je_id"),
            nullable=False,
        ),
        sa.Column("amount_aed", sa.Numeric(18, 2), nullable=False),
        sa.Column("original_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("payment_currency", DISBURSEMENT_CURRENCY, nullable=False),
        sa.Column("bank_ref", sa.Text(), nullable=True),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("period", sa.String(7), sa.ForeignKey("master.periods.period"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("amount_aed > 0", name="disbursement_amount_pos"),
        schema="subledger",
    )
    op.create_index(
        "ix_tutor_disbursements_tutor_id",
        "tutor_disbursements",
        ["tutor_id"],
        schema="subledger",
    )
    op.create_index(
        "ix_tutor_disbursements_period",
        "tutor_disbursements",
        ["period"],
        schema="subledger",
    )

    # =========================================================================
    # 7. master.budget_entries — budget vs. actual module
    # =========================================================================
    op.create_table(
        "budget_entries",
        sa.Column("budget_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("period", sa.String(7), sa.ForeignKey("master.periods.period"), nullable=False),
        sa.Column(
            "account_code",
            sa.String(4),
            sa.ForeignKey("master.chart_of_accounts.code"),
            nullable=False,
        ),
        sa.Column("amount_aed", sa.Numeric(18, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("period", "account_code", name="uq_budget_period_account"),
        sa.CheckConstraint(
            "period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'",
            name="budget_period_format",
        ),
        schema="master",
    )

    # =========================================================================
    # 8. staging.lms_sync_log — LMS polling run history
    # =========================================================================
    op.create_table(
        "lms_sync_log",
        sa.Column("sync_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("since_date", sa.Date(), nullable=False),
        sa.Column("sessions_fetched", sa.Integer(), nullable=True),
        sa.Column("sessions_posted", sa.Integer(), nullable=True),
        sa.Column("sessions_skipped", sa.Integer(), nullable=True),
        sa.Column("sessions_quarantined", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'running'"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'done', 'failed')",
            name="lms_sync_log_status_valid",
        ),
        schema="staging",
    )

    # =========================================================================
    # 9. New audit_action enum values (PG 16 allows ALTER TYPE inside txn)
    # =========================================================================
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'UPLOAD_SESSIONS'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'DISBURSE_PAYROLL'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'BUDGET_POST'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'LOGIN_TOTP'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'UPLOAD_ENROLLMENTS'")


def downgrade() -> None:
    op.drop_table("lms_sync_log", schema="staging")
    op.drop_table("budget_entries", schema="master")
    op.drop_table("tutor_disbursements", schema="subledger")
    op.drop_table("manual_uploads", schema="staging")
    op.drop_table("attachments", schema="staging")
    op.drop_index("ix_chat_messages_session_id", table_name="chat_messages", schema="audit")
    op.drop_table("chat_messages", schema="audit")
    op.drop_table("chat_sessions", schema="audit")
    op.drop_index("ix_sessions_occurred_on", table_name="sessions", schema="master")
    op.drop_index("ix_sessions_enrollment_id", table_name="sessions", schema="master")
    op.drop_table("sessions", schema="master")
    op.drop_index("ix_uq_je_source_ref", table_name="journal_entries", schema="ledger")

    bind = op.get_bind()
    SESSION_STATUS.drop(bind, checkfirst=True)
    UPLOAD_SOURCE_KIND.drop(bind, checkfirst=True)
    UPLOAD_STATUS.drop(bind, checkfirst=True)
    DISBURSEMENT_CURRENCY.drop(bind, checkfirst=True)
