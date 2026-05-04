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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


def reset_settings_cache() -> None:
    """Drop the cached settings (used by tests that override env vars)."""
    get_settings.cache_clear()
