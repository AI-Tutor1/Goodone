-- =============================================================================
-- Tuitional Finance — Postgres bootstrap
-- =============================================================================
-- This file runs ONCE on the first boot of the Postgres container (mounted at
-- /docker-entrypoint-initdb.d/init.sql by docker-compose.yml). It creates the
-- seven application schemas so the Alembic migration does not need superuser
-- privileges to do schema-level DDL. Tables are owned by the migration.
--
-- In production (VPS, no docker-compose), the equivalent commands run once at
-- DB provisioning time per infra/deploy.md.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS master       AUTHORIZATION tuitional;
CREATE SCHEMA IF NOT EXISTS ledger       AUTHORIZATION tuitional;
CREATE SCHEMA IF NOT EXISTS subledger    AUTHORIZATION tuitional;
CREATE SCHEMA IF NOT EXISTS assets       AUTHORIZATION tuitional;
CREATE SCHEMA IF NOT EXISTS sanctions    AUTHORIZATION tuitional;
CREATE SCHEMA IF NOT EXISTS audit        AUTHORIZATION tuitional;
CREATE SCHEMA IF NOT EXISTS staging      AUTHORIZATION tuitional;

-- search_path so unqualified names resolve in the right order.
ALTER ROLE tuitional SET search_path = master, ledger, subledger, assets, sanctions, audit, staging, public;

-- A small extension we lean on for JSONB GIN indexes (built into PG 16 already,
-- listed here so a future swap to a slimmer image still works).
CREATE EXTENSION IF NOT EXISTS pg_trgm;
