---
description: Re-run the Phase 2 / M1 verification gate (lint + format check + unit tests + integration tests + offline migration SQL).
---

Run the M1 verification recipe end-to-end and report pass/fail per check.

Steps:

1. `make install` to ensure uv-managed deps are current.
2. `make lint` — ruff check + ruff format --check across `src tests migrations`.
3. `make type-check` — mypy strict on `src`.
4. `make test` — unit tests (no DB).
5. `make db-up && make migrate` — bring up Postgres and apply migrations to head.
6. `make test-int` — integration tests against the real DB.
7. Render the migration to SQL for review:
   `DATABASE_URL="postgresql+psycopg://x:x@x/x" uv run alembic upgrade head --sql > docs/build/0001_initial.rendered.sql`
8. Sanity-check the rendered SQL: 20 CREATE TYPE, 24 CREATE TABLE (incl. alembic_version),
   17 CHECK, 7 CREATE INDEX, 2 trigger artifacts.

If any step fails, stop and report with the exact command + tail of the error.
