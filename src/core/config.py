"""Application configuration.

Reads settings from environment variables (or a ``.env`` file in dev). Single
``Settings`` object exposed via :func:`get_settings`. No module-level side
effects so tests can override.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
DEFAULT_COA_PATH: Path = REPO_ROOT / "docs" / "chart_of_accounts.yaml"


class Settings(BaseSettings):
    """Strongly-typed app settings.

    Phase 2 only consumes a small subset of the full ``.env.example``; the
    remainder is loaded but unused until later phases. Unknown env vars are
    ignored so we don't have to mirror the full template here.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = Field(default="development")
    database_url: str = Field(
        default="postgresql+psycopg://tuitional:tuitional@localhost:5432/tuitional"
    )
    test_database_url: str | None = Field(default=None)
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json")  # "json" | "console"

    secret_key: SecretStr = Field(default=SecretStr("dev-secret-do-not-use-in-prod"))
    session_lifetime_hours: int = Field(default=8)
    cfo_username: str = Field(default="cfo")
    cfo_password: SecretStr = Field(default=SecretStr("change-me-on-first-boot"))

    coa_path: Path = Field(default=DEFAULT_COA_PATH)

    period_close_auto_close_day: int = Field(default=5)
    period_close_auto_close: bool = Field(default=True)

    capitalization_threshold_aed: int = Field(default=1000)
    tuitional_ai_dev_monthly_aed: int = Field(default=2000)

    # CFO chat
    chat_provider: str = Field(default="stub")  # "stub" | "anthropic"
    chat_model: str = Field(default="claude-sonnet-4-6")
    anthropic_api_key: SecretStr | None = Field(default=None)

    # File uploads
    attachments_dir: Path = Field(default=REPO_ROOT / "attachments")
    attachments_max_size_mb: int = Field(default=20)

    # TOTP — set cfo_totp_secret to a base32 string (pyotp.random_base32()) and
    # totp_enforced=true in production to require OTP on every login.
    cfo_totp_secret: SecretStr | None = Field(default=None)
    totp_enforced: bool = Field(default=False)

    # FA (Finance Admin) role — separate from CFO; can approve sanctions / view reports
    fa_username: str | None = Field(default=None)
    fa_password: SecretStr | None = Field(default=None)
    fa_email: str | None = Field(default=None)
    cfo_email: str | None = Field(default=None)

    # Email notifications
    email_provider: str = Field(default="stub")  # "stub" | "smtp" | "sendgrid" | "ses"
    email_from_address: str = Field(default="finance@tuitional.example")
    email_from_name: str = Field(default="Tuitional Finance")
    smtp_host: str | None = Field(default=None)
    smtp_port: int = Field(default=587)
    smtp_username: str | None = Field(default=None)
    smtp_password: SecretStr | None = Field(default=None)
    sendgrid_api_key: SecretStr | None = Field(default=None)
    ses_region: str | None = Field(default=None)

    # LMS adapter
    lms_api_base_url: str | None = Field(default=None)
    lms_api_key: SecretStr | None = Field(default=None)
    lms_poll_interval_minutes: int = Field(default=60)

    # Google Sheets — ad spend (existing) + sessions + enrollments
    google_service_account_json_path: str | None = Field(default=None)
    google_sheets_ad_spend_id: str | None = Field(default=None)
    google_sheets_ad_spend_tab: str = Field(default="ad_spend")
    google_sheets_sessions_id: str | None = Field(default=None)
    google_sheets_sessions_tab: str = Field(default="sessions")
    google_sheets_enrollments_id: str | None = Field(default=None)
    google_sheets_enrollments_tab: str = Field(default="enrollments")

    # FX
    fx_api_key: SecretStr | None = Field(default=None)
    fx_base_currency: str = Field(default="AED")

    # Backup
    backup_dir: Path = Field(default=Path("/var/backups/tuitional"))

    # Budget period lock — when True, CFO must explicitly unlock before editing budget
    budget_period_lock: bool = Field(default=False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


def reset_settings_cache() -> None:
    """Drop the cached settings (used by tests that override env vars)."""
    get_settings.cache_clear()
