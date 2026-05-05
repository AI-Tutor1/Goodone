.DEFAULT_GOAL := help

PYTHON := uv run python
PYTEST := uv run pytest
RUFF := uv run ruff
MYPY := uv run mypy
ALEMBIC := uv run alembic

.PHONY: help
help:
	@echo "Tuitional Finance — common tasks"
	@echo ""
	@echo "Setup:"
	@echo "  install         Install Python deps (uv sync)"
	@echo "  db-up           Start local Postgres via docker-compose"
	@echo "  db-down         Stop local Postgres"
	@echo "  migrate         Run Alembic migrations to head"
	@echo ""
	@echo "Development:"
	@echo "  api             Run FastAPI dev server (port 8000)"
	@echo "  worker          Run worker process for agents"
	@echo "  lint            Run ruff check + format check"
	@echo "  format          Auto-format with ruff"
	@echo "  type-check      Run mypy"
	@echo ""
	@echo "Testing:"
	@echo "  test            Run unit tests"
	@echo "  test-int        Run integration tests (requires Postgres)"
	@echo "  smoketest       Run the golden scenario smoketest"
	@echo "  cov             Run tests with coverage report"
	@echo ""
	@echo "Quality:"
	@echo "  check           Run lint + type-check + test"
	@echo "  security        Run bandit + safety"

.PHONY: install
install:
	uv sync --all-groups

.PHONY: db-up
db-up:
	docker compose up -d postgres

.PHONY: db-down
db-down:
	docker compose down

.PHONY: migrate
migrate:
	$(ALEMBIC) upgrade head

APP_PORT ?= 3001

.PHONY: api
api:
	$(PYTHON) -m uvicorn src.api.main:app --reload --host 127.0.0.1 --port $(APP_PORT)

.PHONY: worker
worker:
	$(PYTHON) -m src.worker

.PHONY: lint
lint:
	$(RUFF) check .
	$(RUFF) format --check .

.PHONY: format
format:
	$(RUFF) check --fix .
	$(RUFF) format .

.PHONY: type-check
type-check:
	$(MYPY) src

.PHONY: test
test:
	$(PYTEST) -q -m "not integration and not smoketest"

.PHONY: test-int
test-int:
	$(PYTEST) -q -m integration

.PHONY: smoketest
smoketest:
	$(PYTEST) -q -m smoketest

.PHONY: seed-dev
seed-dev:
	$(PYTHON) -m scripts.seed_dev_data

.PHONY: render-sql
render-sql:
	DATABASE_URL="postgresql+psycopg://x:x@x/x" \
	  $(ALEMBIC) upgrade head --sql > docs/build/0001_initial.rendered.sql
	@echo "rendered → docs/build/0001_initial.rendered.sql"

.PHONY: cov
cov:
	$(PYTEST) --cov=src --cov-report=term-missing --cov-report=html

.PHONY: check
check: lint type-check test

.PHONY: security
security:
	uv run bandit -r src -ll
	uv run safety check
