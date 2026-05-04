"""Alembic environment.

Two modes:

* **online** — connect to the URL from ``Settings.database_url`` and run
  migrations against the live DB.
* **offline** — emit SQL to stdout (used for review / archive).

The migration uses *raw* DDL (``op.execute``) rather than autogenerate from ORM
models because the schema for Phase 2 is hand-tuned (CHECK constraints,
triggers, named enums, GIN indexes) — autogenerate noise would obscure the
intent. We also keep :class:`Base.metadata` empty here so a future autogenerate
diff is meaningful only after we wire ORM models.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from src.core.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Pull the URL from app settings unless one was explicitly set on the CLI.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = None  # raw-DDL migrations; ORM models wired in a later phase


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
