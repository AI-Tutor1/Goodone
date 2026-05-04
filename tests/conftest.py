"""Shared pytest fixtures.

Two database modes:

* **Unit tests** (default) — no DB. Pure Python.
* **Integration tests** (``-m integration``) — testcontainers spin up a real
  Postgres 16, the migration runs once per session, and each test runs in a
  SAVEPOINT that is rolled back at teardown so tests don't pollute each other.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def coa_yaml_path(repo_root: Path) -> Path:
    return repo_root / "docs" / "chart_of_accounts.yaml"


# ---------------------------------------------------------------------------
# Integration-test infrastructure (skipped if Docker / testcontainers absent)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    """A Postgres URL backed by a real container.

    Uses testcontainers if available; falls back to ``TEST_DATABASE_URL`` env
    var (set by CI / docker-compose) so developers without Docker can still run
    the suite against a manually-started Postgres.
    """
    import os

    env_url = os.environ.get("TEST_DATABASE_URL")
    if env_url:
        yield env_url
        return

    try:
        from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]
    except ImportError:
        pytest.skip("testcontainers not installed and TEST_DATABASE_URL not set")

    container = PostgresContainer(
        "postgres:16-alpine", username="tuitional", password="tuitional", dbname="tuitional"
    )
    container.start()
    try:
        url = container.get_connection_url().replace("postgresql://", "postgresql+psycopg://")
        # Ensure the seven schemas exist (mirrors infra/postgres/init.sql).
        engine = create_engine(url, future=True)
        with engine.begin() as conn:
            for schema in (
                "master",
                "ledger",
                "subledger",
                "assets",
                "sanctions",
                "audit",
                "staging",
            ):
                conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        engine.dispose()
        yield url
    finally:
        container.stop()


@pytest.fixture(scope="session")
def migrated_engine(pg_url: str) -> Iterator[Engine]:
    """Run the Alembic migration once and hand back an Engine."""
    import os

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", pg_url)
    os.environ["DATABASE_URL"] = pg_url
    command.upgrade(cfg, "head")

    engine = create_engine(pg_url, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_session(migrated_engine: Engine) -> Iterator[Session]:
    """Per-test SAVEPOINT-rolled-back session.

    Pattern lifted from SQLAlchemy docs: open a connection + outer
    transaction, bind a Session to it, and roll back on teardown so tests
    never see each other's writes.
    """
    connection = migrated_engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(bind=connection, expire_on_commit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
