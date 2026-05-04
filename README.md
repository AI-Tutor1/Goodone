# Tuitional Finance

Autonomous finance department for Tuitional Education — double-entry general ledger, payroll, revenue recognition, FX, reporting, and budget controls. Single-entity, AED functional currency, PKR tutor payments. Single CFO consumer initially; role-based access ready for later expansion.

This repository is the **build-and-handover** package: complete codebase, schema, docs, and deployment runbook. Deployment to the VPS is operator-managed (you).

## Status

**Phases 1 → 6 complete.** All build phases shipped. The remaining work is
the operator-side production cutover (run `infra/deploy.md` and complete
the parallel-operations sign-off described in `docs/plan.md` §11).

Phase progression:

1. ✅ Foundation docs + repo skeleton
2. ✅ Database schema + ledger engine + partial smoketest
3. ✅ Ingestion adapters + validation layer
4. ✅ Domain agents (revenue, payroll, FX, depreciation, amortization, sanctions, reporting, profitability, period close)
5. ✅ FastAPI backend with auth + React/Vite/Tailwind CFO dashboard on port 3002 (API) / 5173 (web), plus read-only **CFO chat** (LLM with GL tools)
6. ✅ CI/CD + Docker images + Prometheus observability + Grafana dashboards + backup/restore + VPS deploy runbook

Phase 2 milestones (per `docs/plan.md` and the working spec):

| # | Milestone | Status |
|---|---|---|
| M1 | Repo bootstrap + Alembic migration `0001_initial` + COA loader + first unit tests | ✅ |
| M2 | Posting service (`src/ledger/posting.py`) with full validation + audit row on every attempt | ✅ |
| M3 | Sub-ledger registry + six concrete sub-ledgers (`src/subledgers/*`) | ✅ |
| M4 | Period state machine (`src/ledger/period.py`) + reversal helper | ✅ |
| M5 | Hypothesis property-based suite (5 properties) | ✅ |
| M6 | Seed dev-data script + Phase-2 partial smoketest + golden file | ✅ |

**Numbers, end of Phase 2.** 24 application tables across 7 schemas (master / ledger / subledger / assets / sanctions / audit / staging); 20 named enums; 17 CHECK constraints (Dr=Cr, debit-XOR-credit, narration ≥ 10 chars, attachment-policy gate, reopen-reason ≥ 30, period-format `YYYY-MM`, etc.); 7 indexes incl. 2 GIN on JSONB; one wallet-non-negative deferred-constraint trigger; COA YAML loader (idempotent two-pass); a deterministic posting service with 9-step validation and audit-row-on-every-attempt; six sub-ledgers with per-key reconciliation; period state machine with hard-block on reconciliation mismatch + attachment offenders; reversal helper; 5-property hypothesis suite (balance / reconciliation / reversal / no-negative-wallet / immutability); partial smoketest covering 48 JEs + the canonical 46/60/2500 penalty case. **77 passing unit tests** in this sandbox; integration + property + smoketest suites need a real Postgres (use `make test-int` / `make smoketest` on a machine with Docker).

See `docs/plan.md` for the long-form phase plan and `INDEX.md` for a flat file map.

## Quick orientation

If you read only four documents, read these in order:

1. `docs/context.md` — what Tuitional does, glossary, business model
2. `docs/architecture.md` — system layers, agent boundaries, data flow
3. `docs/chart_of_accounts.md` (and the YAML beside it) — the spine of the ledger
4. `docs/accounting_rules.md` — every business event mapped to a journal entry

Everything else (rules, design, QA, runbooks) hangs off those four.

## Stack (locked in Phase 1)

- **Language:** Python 3.11+ (calc engine, ledger, agents) + TypeScript (frontend only)
- **Backend:** FastAPI
- **Database:** PostgreSQL 16
- **Frontend:** React 18 + Vite + Tailwind CSS
- **Migrations:** Alembic
- **Testing:** pytest, pytest-cov, hypothesis (for property-based tests on ledger math)
- **Linting:** ruff (Python), eslint (TS)
- **Type-checking:** mypy strict (Python), TypeScript strict
- **Email:** Provider abstraction; stubbed in dev; SES/SendGrid/SMTP swappable
- **Deployment target:** Ubuntu 24.04 VPS, systemd-managed services, Postgres on same box (or managed)
- **Observability:** structured JSON logs (stdout) + OpenTelemetry-ready instrumentation

## Repository layout (current — Phase 2 / M1)

```
tuitional-finance/
├── README.md                       this file
├── INDEX.md                        flat map of every file
├── CLAUDE.md                       hard rules + workflow for any LLM agent
├── pyproject.toml                  Python project config (uv-managed)
├── Makefile                        install / migrate / lint / type-check / test / smoketest
├── docker-compose.yml              local dev: Postgres 16 + Adminer + ephemeral test DB
├── alembic.ini                     migration config
├── .env.example                    required environment variables
├── .gitignore
├── docs/                           the spec — read before coding
│   ├── context.md / architecture.md / plan.md / ifrs_treatments.md
│   ├── chart_of_accounts.yaml      source of truth for the COA (loaded into DB)
│   ├── chart_of_accounts.md        prose companion
│   ├── accounting_rules.md         every event → JE; §13 paired-account memo; §17 attachment policy
│   ├── rules/                      journal / period-close / approval / ingestion rules
│   ├── design/                     api / frontend / responsiveness specs (Phase 5)
│   ├── qa/                         test_plan + smoketests (§7 = Phase-2 partial)
│   ├── runbooks/                   month-end close / period reopen / FX override / DR
│   └── build/                      generated artifacts (rendered SQL etc.)
├── .claude/conductor/              workflow context for Claude Code's /conductor flow
├── .github/workflows/              CI/CD pipelines
├── infra/
│   ├── postgres/init.sql           creates the seven schemas on first boot
│   ├── systemd/                    production unit files
│   └── deploy.md                   VPS runbook (full version in Phase 6)
├── migrations/
│   ├── env.py / script.py.mako
│   └── versions/0001_initial.py    Phase-2 schema (24 tables, 20 enums, 17 CHECKs)
├── src/
│   ├── core/                       config / db / money / exceptions / logging
│   ├── ledger/                     coa.py + coa_loader.py (M1); posting.py + period.py + subledger.py (M2–M4)
│   ├── subledgers/                 per-sub-ledger logic (M3)
│   ├── ingestion/                  Phase 3
│   ├── validation/                 Phase 3
│   ├── agents/                     Phase 4
│   ├── api/                        Phase 5
│   ├── chat/                       Phase 5 (CFO chat; LLM read-only)
│   └── email/                      Phase 5 (provider abstraction)
├── tests/
│   ├── conftest.py                 testcontainers-backed DB fixtures + per-test rollback
│   ├── core/                       money helpers
│   ├── ledger/                     COA loader unit tests
│   ├── db/                         migration + COA-DB integration tests
│   ├── properties/                 hypothesis suite (M5)
│   ├── smoketest/phase2/           Phase-2 partial smoketest (M6)
│   ├── factories/                  factory-boy factories (M3+)
│   ├── fixtures/smoketest/phase2/  golden file lives here (M6)
│   └── test_no_float.py            static guard against float in calc core
└── scripts/                        Phase-2 / M5+ — seed_dev_data.py
```

## How to use this repo

1. **Install + migrate.** `make install && make db-up && make migrate` (`make help` for everything).
2. **Seed dev data.** `make seed-dev` lays down opening balances + top-ups + sessions + the canonical penalty case for the partial smoketest.
3. **Run the status API.** `make api` boots the Phase-2 status server on **`http://localhost:3002`**. Endpoints: `/` (health + COA version), `/coa`, `/coa/{code}`, `/db/health`, `/periods/{period}`, `/reconcile`. OpenAPI docs at `/docs`. Override the port with `make api APP_PORT=4000`.
4. **Run the suite.** `make test` (unit, no DB) → `make test-int` (Docker required) → `make smoketest` for the golden scenario.
5. **Read the spec before coding.** Order: `docs/context.md` → `docs/architecture.md` → `docs/chart_of_accounts.{yaml,md}` → `docs/accounting_rules.md` → the relevant `docs/rules/*.md`.
6. **Red-line `docs/` before code.** If the spec is wrong, fix the spec first and the code follows.
7. **The YAML wins.** `docs/chart_of_accounts.yaml` is the source of truth for the COA; the loader writes it to the DB.

## Local deploy in one stanza

```bash
make install                                  # uv sync --all-groups
make db-up                                    # docker compose up -d postgres
make migrate                                  # alembic upgrade head
make seed-dev                                 # opening balances + sample data
make api                                      # uvicorn on http://localhost:3002
# in another shell:
cd frontend && npm install && npm run dev     # CFO dashboard on http://localhost:5173
```

The Vite dev server proxies `/api/*` → `http://localhost:3002`, so the
dashboard talks to the backend without CORS configuration in dev. Default
CFO credentials come from `.env` (`CFO_USERNAME` / `CFO_PASSWORD`); change
them on first boot.

## Deployment

You deploy. `infra/deploy.md` is the full step-by-step runbook for a fresh
Ubuntu 24.04 VPS — provisioning, Postgres, application config, Docker
builds, systemd units, nginx + Let's Encrypt, backup restore drill, and
production smoketest. Estimated end-to-end time: 60–90 minutes.

CI is green on `main` for every push: backend lint + format + mypy + 96
unit tests + bandit + safety + offline SQL render, frontend typecheck +
build, and Docker image builds for backend and frontend
(`infra/docker/{backend,frontend}.Dockerfile`,
`infra/docker/docker-compose.prod.yml`). Prometheus scrapes
`/api/metrics` every 30s; alert rules in `infra/prometheus/alerts.yml`
cover backend down, high rejection rate, p99 latency, quarantine growth,
backup age, FX rate staleness, and period-close failure. Daily database
backups run via `tuitional-backup.timer`; the restore drill (Phase-6
acceptance criterion) lives in `scripts/restore.sh` and asserts a zero
trial-balance after replay.

## License

Proprietary. Tuitional Education internal use only.
