# File Index

A flat map of every file in the repo, grouped by purpose. Use this as the
navigation hub when you don't yet know where a thing lives.

## Top-level repo metadata

| Path | What it is |
|---|---|
| `README.md` | Project overview, status, repo layout, deployment notes |
| `CLAUDE.md` | Context file for Claude Code (and any LLM agent) — hard rules, workflow, code style |
| `INDEX.md` | This file |
| `.gitignore` | Standard Python + venv + frontend ignores |
| `.env.example` | Template for `.env` (DB URL, secrets, FX, email, etc.) |
| `pyproject.toml` | Python project config — deps, ruff, mypy, pytest, coverage |
| `Makefile` | `make install / db-up / migrate / lint / type-check / test / smoketest` |
| `docker-compose.yml` | Local dev stack: Postgres 16 + Adminer + ephemeral test DB |
| `alembic.ini` | Alembic migration config |

## Domain documentation (`docs/`)

Read these before touching code. Order: `context.md` → `architecture.md` → COA → rules.

| Path | What it is |
|---|---|
| `docs/context.md` | Business model, glossary, Tuitional domain (50k students, AED, PKR tutors, wallets, sessions, FX, fixed assets) |
| `docs/architecture.md` | Five-layer system; component responsibilities; module → directory map |
| `docs/plan.md` | Phases 1–6 with deliverables and acceptance criteria |
| `docs/ifrs_treatments.md` | IFRS 15/16/IAS 38 application notes |
| `docs/chart_of_accounts.yaml` | **Source of truth** for the COA (loaded into the DB by `src/ledger/coa_loader.py`) |
| `docs/chart_of_accounts.md` | Prose companion to the YAML — numbering convention, sub-ledgers, design rationale |
| `docs/accounting_rules.md` | Every business event → journal entry, including the §13 paired-account memo (2060/9010) and §17 attachment policy |

## Specification rules (`docs/rules/`)

| Path | What it is |
|---|---|
| `docs/rules/journal_rules.md` | Engine invariants: balance, postability, period status, sub-ledger consistency, source attribution, immutability, reconciliation guarantees |
| `docs/rules/period_close_rules.md` | T+5 cycle, pre-close steps, hard blocks, reopen workflow, year-end |
| `docs/rules/approval_rules.md` | Sanction workflow (department head → FA → CFO) |
| `docs/rules/ingestion_rules.md` | Validation + quarantine rules for ingest layer (Phase 3) |

## Design specs (`docs/design/`)

| Path | What it is |
|---|---|
| `docs/design/api_design.md` | FastAPI shape (Phase 5) |
| `docs/design/frontend_design.md` | CFO Dashboard spec (Phase 5) |
| `docs/design/responsiveness.md` | Tablet + desktop breakpoints (Phase 5) |

## Quality specs (`docs/qa/`)

| Path | What it is |
|---|---|
| `docs/qa/test_plan.md` | Test pyramid, coverage targets, property-based suite, smoketest, security/perf |
| `docs/qa/smoketests.md` | Golden 30-day scenario; §7 is the Phase-2 partial that M8 ships |

## Operational runbooks (`docs/runbooks/`)

| Path | What it is |
|---|---|
| `docs/runbooks/month_end_close.md` | T+1 → T+5 month-end SOP |
| `docs/runbooks/period_reopen.md` | CFO reopen procedure |
| `docs/runbooks/fx_rate_override.md` | Manual FX rate override SOP |
| `docs/runbooks/disaster_recovery.md` | Backup + restore drill |

## Build artifacts (`docs/build/`) — generated, regenerate via Make/Alembic

| Path | What it is |
|---|---|
| `docs/build/0001_initial.rendered.sql` | The Phase-2 migration rendered to plain SQL via `alembic upgrade head --sql`. Regenerate with `DATABASE_URL=postgresql+psycopg://x:x@x/x alembic upgrade head --sql > docs/build/0001_initial.rendered.sql` |

## Application code (`src/`)

Phase 2 / M1 lands the foundation. Other directories are `__init__.py`-only stubs awaiting later phases.

| Path | What it is | Phase |
|---|---|---|
| `src/core/config.py` | `Settings` (pydantic-settings); `get_settings()` singleton | 2 |
| `src/core/db.py` | SQLAlchemy 2.x engine, session factory, naming convention, `session_scope()` | 2 |
| `src/core/money.py` | `aed()`, `pkr()`, `fx_rate()` — Decimal helpers; rejects `float` | 2 |
| `src/core/exceptions.py` | `LedgerError` hierarchy (Validation/Period/SubLedger/Immutability/Reversal/COAValidation) | 2 |
| `src/core/logging.py` | structlog configure + `get_logger()` | 2 |
| `src/ledger/coa.py` | YAML → in-memory `COA` model with `validate_structure()`; process-wide singleton | 2 ✅ |
| `src/ledger/coa_loader.py` | DB upsert (idempotent); two-pass parents-before-children to avoid self-FK violations | 2 ✅ |
| `src/ledger/posting.py` | `post_journal()` + `reverse_journal()` with full validation, audit row on every attempt | 2 ✅ |
| `src/ledger/subledger.py` | Sub-ledger `Protocol` + registry; `signed_delta`; `ReconciliationResult`; `build_default_registry()` | 2 ✅ |
| `src/ledger/period.py` | `OPEN → IN_CLOSING → CLOSED → REOPENED` state machine; `close()` runs reconciliation + snapshot | 2 ✅ |
| `src/subledgers/student_wallet.py` | 2050 wallet sub-ledger (credit-normal, deferred wallet-non-negative trigger) | 2 ✅ |
| `src/subledgers/tutor_payable.py` | 2020 PKR + 2030 AED with original-currency / fx-rate per row | 2 ✅ |
| `src/subledgers/fixed_asset.py` | 1111/1113/1115 cost + 1112/1114/1116 accum dep; per-asset NBV | 2 ✅ |
| `src/subledgers/prepaid.py` | 1051 / 1052 prepaids with monthly amortisation entries | 2 ✅ |
| `src/subledgers/intangible.py` | 1121 in-development → 1122 launched → 1123 accum amortisation | 2 ✅ |
| `src/subledgers/sanction_memo.py` | 2060 / 9010 paired-account memo (COMMIT / CONTRA / SPEND_REVERSE) | 2 ✅ |
| `src/ingestion/{lms,sheets,bank,fx,manual_upload}.py` | Adapters | 3 |
| `src/validation/` | Rule engine + quarantine | 3 |
| `src/agents/{revenue,payroll,fx,depreciation,amortization,sanctions,reporting,profitability,period_close}.py` | Domain agents | 4 |
| `src/api/main.py` | Phase-2 status API on port 3002 (`/`, `/coa`, `/coa/{code}`, `/db/health`, `/periods/{period}`, `/reconcile`). Full Phase-5 dashboard expands this surface. | 2 ✅ |
| `src/chat/__init__.py` | Public exports for the CFO chat module | 5 ✅ |
| `src/chat/models.py` | Pydantic models — `ChatMessage`, `ChatSession`, `ChatTurnRequest`, `ChatTurnResponse`, `ToolDescriptor` | 5 ✅ |
| `src/chat/tools.py` | Read-only GL tool registry — `get_account_balance`, `get_pnl`, `get_trial_balance`, `get_period_status`, `list_open_sanctions`, `list_quarantine`, `list_recent_journals` | 5 ✅ |
| `src/chat/provider.py` | LLM provider abstraction — `StubChatProvider` (deterministic, offline) and `AnthropicChatProvider` (opt-in via `CHAT_PROVIDER=anthropic`) | 5 ✅ |
| `src/chat/service.py` | Turn orchestrator + `InMemorySessionStore`; bounded by `MAX_TOOL_ROUNDS=3` | 5 ✅ |
| `src/api/routes/chat.py` | `POST /chat/sessions`, `POST /chat/sessions/{id}/messages`, `GET /chat/sessions/{id}`, `GET /chat/tools` | 5 ✅ |
| `src/email/` | Provider abstraction (stub / SMTP / SendGrid / SES) | 5 |

## Database migrations (`migrations/`)

| Path | What it is |
|---|---|
| `migrations/env.py` | Alembic env: pulls URL from `Settings.database_url`; raw-DDL approach |
| `migrations/script.py.mako` | New-revision template |
| `migrations/versions/0001_initial.py` | Phase-2 schema: master / ledger / subledger / assets / sanctions / audit / staging |

## Tests (`tests/`)

| Path | What it is | Marker |
|---|---|---|
| `tests/conftest.py` | Session-scoped Postgres (testcontainers) + per-test SAVEPOINT rollback fixture | — |
| `tests/core/test_money.py` | Decimal helpers; AED/PKR/FX quantization; float-rejection | unit |
| `tests/ledger/test_coa.py` | YAML loader, validation rules, range/type checks, memo accounts, idempotent reload | unit |
| `tests/db/test_migration.py` | Schema + table presence; CHECK constraints reject bad rows | integration |
| `tests/db/test_coa_loader.py` | Loader writes every account; idempotent on rerun; round-trip of memo (9010) | integration |
| `tests/db/test_posting_integration.py` | Full post_journal + reverse_journal + sub-ledger application | integration |
| `tests/db/test_period_integration.py` | PeriodService end-to-end (open / closing / close / reopen / blockers) | integration |
| `tests/ledger/test_posting_validation.py` | Pre-DB validators in posting.py (shape / COA / balance / attachment policy) | unit |
| `tests/ledger/test_period_format.py` | Period format helper + iter_months | unit |
| `tests/ledger/test_subledger_helpers.py` | signed_delta + per-sub-ledger classify helpers | unit |
| `tests/test_no_float.py` | Static guard: `float(` and `: float` forbidden in `src/ledger/`, `src/subledgers/` | unit |
| `tests/properties/test_balance_invariant.py` | Hypothesis: any random topup leaves trial balance == 0 | integration |
| `tests/properties/test_reconciliation_invariant.py` | Hypothesis: 2050 reconciles to wallet sub-ledger after random sequences | integration |
| `tests/properties/test_reversal_correctness.py` | Hypothesis: post + reverse → balance unchanged | integration |
| `tests/properties/test_no_negative_wallet.py` | Hypothesis: consume > balance always rejected | integration |
| `tests/properties/test_immutability.py` | Hypothesis: posted columns stable across other writes; closed period rejects all drafts | integration |
| `tests/smoketest/phase2/test_partial.py` | Phase-2 partial smoketest (golden-file diff) | smoketest |
| `tests/factories/__init__.py` | Public factory exports — `JournalEntryDraftFactory`, `JournalLineDraftFactory`, `AccountFactory`, `WalletAccountFactory`, `HeaderAccountFactory`, `StudentFactory`, `TutorFactory`, `FxRateFactory`, `ManualFxRateFactory` | unit |
| `tests/factories/journals.py` | `JournalEntryDraftFactory` + `JournalLineDraftFactory` (default produces a balanced 2-line entry) | unit |
| `tests/factories/coa.py` | `AccountFactory`, `WalletAccountFactory` (sub-ledger 2050), `HeaderAccountFactory` (non-postable) | unit |
| `tests/factories/people.py` | `StudentFactory`, `TutorFactory` — DictFactory rows shaped like `master.students` / `master.tutors` | unit |
| `tests/factories/fx.py` | `FxRateFactory`, `ManualFxRateFactory` for `ledger.fx_rates` | unit |
| `tests/test_factories.py` | Smoke tests — every factory builds with no kwargs and produces the expected default | unit |
| `tests/chat/test_chat_service.py` | Orchestration tests — capabilities reply, tool routing, history persistence, unknown-tool surface, descriptor coverage | unit |
| `tests/chat/test_stub_provider.py` | Stub provider keyword-routing + input extraction (account_code, period) | unit |
| `tests/fixtures/smoketest/phase2/expected.json` | Phase-2 golden file (committed, hand-curated) | — |

## Infrastructure (`infra/`)

| Path | What it is | Phase |
|---|---|---|
| `infra/postgres/init.sql` | Creates the seven schemas on docker-compose first boot | 2 |
| `infra/systemd/tuitional-api.service` | Production systemd unit for the API | 2 |
| `infra/systemd/tuitional-worker.service` | Production systemd unit for the worker | 2 |
| `infra/systemd/tuitional-backup.service` | Daily `pg_dump` oneshot, runs `scripts/backup.sh` with `/etc/tuitional/backup.env` | 6 ✅ |
| `infra/systemd/tuitional-backup.timer` | OnCalendar 02:30 UTC daily, `Persistent=true` | 6 ✅ |
| `infra/docker/backend.Dockerfile` | Multi-stage build: `python:3.11-slim-bookworm` + uv builder, slim runtime as uid 10001 `tuitional`, `HEALTHCHECK`, uvicorn on 3002 | 6 ✅ |
| `infra/docker/frontend.Dockerfile` | `node:20-bookworm-slim` builder runs `npm run build`; runtime is `nginx:1.27-alpine` serving `dist/` | 6 ✅ |
| `infra/docker/nginx.conf` | SPA fallback, `/assets/` long-cache immutable, `/api/` reverse-proxy to `backend:3002`, security headers | 6 ✅ |
| `infra/docker/docker-compose.prod.yml` | Postgres + backend + frontend + Prometheus stack for prod-shaped local repro | 6 ✅ |
| `infra/prometheus/prometheus.yml` | Scrape config: `backend:3002/metrics` every 30s; references `alerts.yml` | 6 ✅ |
| `infra/prometheus/alerts.yml` | 7 rules — BackendDown, HighRejectionRate, HighLatencyP99, QuarantineGrowing, BackupAgeStale, FxRateMissingForToday, PeriodCloseRunFailed | 6 ✅ |
| `infra/grafana/README.md` | Import + provisioning notes for the dashboard JSON files | 6 ✅ |
| `infra/grafana/tuitional-overview.json` | Grafana dashboard — HTTP rate, p50/p99 latency, 5xx rate, in-flight, top routes | 6 ✅ |
| `infra/grafana/tuitional-ledger.json` | Grafana dashboard — journals posted/rejected, quarantine open, rejection ratio, cumulative posts | 6 ✅ |
| `infra/deploy.md` | Full VPS deploy runbook for Ubuntu 24.04 (12 sections, 60–90 min end-to-end) | 6 ✅ |

## CI / dev workflow

| Path | What it is |
|---|---|
| `.github/workflows/ci.yml` | Backend (lint + format + mypy + pytest unit/integration/smoketest + coverage ≥85% + bandit + safety + offline SQL render artifact) + frontend (typecheck + build) + yaml-lint + Docker image build matrix |
| `.github/workflows/deploy.yml` | (Optional) tagged-release deploy pipeline — see `infra/deploy.md` for the canonical procedure |
| `.claude/conductor/context.md` | Pointers consumed by the Conductor plugin so `/conductor` knows where the spec lives |

## Scripts (`scripts/`)

| Path | What it is | Phase |
|---|---|---|
| `scripts/seed_dev_data.py` | Loads opening balances + 5 top-ups + 2 refunds + 19 sessions + 1 canonical-penalty session into a fresh DB. Used by `make seed-dev` and the Phase-2 partial smoketest. | 2 |
| `scripts/backup.sh` | `pg_dump` → gzip → sanity-check → 30-day retention prune → optional S3 offsite upload; exits non-zero on failure | 6 ✅ |
| `scripts/restore.sh` | Restore drill: applies `init.sql`, replays latest backup into `TARGET_DATABASE_URL`, asserts trial balance == 0 (exit 3 on mismatch) | 6 ✅ |

## Observability (Phase 6) — `src/api/observability.py`

| Symbol | Type | What it is |
|---|---|---|
| `ObservabilityMiddleware` | `BaseHTTPMiddleware` | Tags every request with an `X-Request-ID` (echoed in response + bound into structlog contextvars), tracks in-flight gauge, observes duration histogram, increments per-(method,path,status) counter, emits structured `http_request` log line |
| `http_requests_total` | counter | `tuitional_http_requests_total{method,path,status}` |
| `http_in_flight` | gauge | `tuitional_http_in_flight` |
| `http_request_duration_seconds` | histogram | Buckets `[5ms, 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s, 2.5s, 5s, 10s]` |
| `journals_posted_total` | counter | `tuitional_journals_posted_total{source_kind}` — bumped on success in `src/ledger/posting.py` |
| `journals_rejected_total` | counter | `tuitional_journals_rejected_total{source_kind, error}` — bumped on rejection |
| `quarantine_open_gauge` | gauge | `tuitional_quarantine_open` — set by validation layer when rows enter `staging.data_quality_quarantine` |
| `render_prometheus()` | function | Plain-text exposition served at `/metrics` |
| `/metrics` | endpoint | `text/plain; version=0.0.4` Prometheus exposition (excluded from OpenAPI schema) |
| `/healthz` | endpoint | Liveness probe (no DB touch) |
