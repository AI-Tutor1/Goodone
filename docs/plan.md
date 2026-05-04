# Build Plan

This is the working schedule for Phases 2–6. Phase 1 (this skeleton) is complete on the date this plan is delivered.

Each phase has: **Deliverables**, **Acceptance criteria**, and **What you must verify before approving**. Phases gate on each other — Phase 3 cannot start until Phase 2 is approved.

## Phase 1 — Foundation (DONE)

**Deliverables:** docs tree, repo skeleton, COA spec, accounting rules spec, IFRS treatments, design notes, runbook stubs, CI/CD stubs.

**Acceptance criteria:**
- All documents in `docs/` reviewed by CFO/CEO
- Chart of accounts approved (this is the highest-stakes sign-off)
- Stack choices confirmed (Postgres, React+Vite+Tailwind, email stubbed)

**What you must verify:** The COA in `docs/chart_of_accounts.yaml` matches your mental model of the business. The accounting rules in `docs/accounting_rules.md` produce the journal entries you expect.

## Phase 2 — Database + Ledger Engine

**Deliverables:**
- PostgreSQL schema (DDL via Alembic migration `0001_initial.py`)
- COA loader (Python module that reads `chart_of_accounts.yaml` into the DB)
- Ledger posting service: `post_journal(entry: JournalEntry) -> PostedJournal`
  - Validates Dr = Cr
  - Validates accounts exist and are postable
  - Validates period is open
  - Atomic write to `journal_entries` + `journal_lines`
  - Updates affected sub-ledgers
- Sub-ledger registries:
  - `StudentWallet` — top-up, consumption, refund, balance, aging
  - `TutorPayable` — accrual, payment, balance per tutor in PKR + AED-translated
  - `FixedAssets` — register, monthly depreciation, NBV
  - `PrepaidSchedule` — schedule, monthly amortization
- Property-based tests with `hypothesis` proving that no sequence of postings ever leaves the GL unbalanced
- Smoketest: 30-day fictional Tuitional ledger that produces a known P&L and BS

**Acceptance criteria:**
- `pytest -q` passes with > 90% coverage on `src/ledger/` and `src/subledgers/`
- The smoketest produces the documented expected output (committed as a golden file)
- A deliberately unbalanced journal entry is rejected with a clear error
- A journal entry posted to a closed period is rejected
- All sub-ledger balances reconcile to their GL control accounts in the smoketest

**What you must verify:** Run `make smoketest` locally, read the generated P&L and BS, confirm the numbers match expectations.

## Phase 3 — Ingestion + Validation

**Deliverables:**
- LMS adapter (interface defined; mock implementation for testing; real implementation requires you to provide LMS API credentials and docs)
- Google Sheets adapter (using a service account JSON; reads ad spend, leads, manual entries from named sheets)
- Bank statement parser (CSV upload, configurable column map for different banks)
- FX rate puller (exchangerate.host daily; manual override UI in Phase 5)
- Validation rule engine: rules expressed in Python, configurable thresholds, quarantine on failure
- Quarantine table + minimal CLI to inspect and reprocess
- One-time historical backfill script for month-1 payroll screenshots (manual CSV input)

**Acceptance criteria:**
- Ingest a fixture LMS payload of 200 sessions; all valid pass through, all invalid quarantine, no duplicates
- FX puller fetches last 30 days; manually-entered override takes precedence over auto value
- Bank CSV with deliberate column-order changes still parses (with config update)
- All adapters are idempotent: running twice on same input produces no duplicates

**What you must verify:** Provide a real LMS sample export. We ingest it, you confirm the parsed sessions match the source.

## Phase 4 — Domain Agents

**Deliverables:**
- **Revenue Agent**: consumes session events, posts revenue journals
- **Payroll Agent**: penalty math, FX accrual, monthly payable schedule, PDF/CSV export of tutor payouts
- **FX Agent**: daily rate management, month-end revaluation of monetary balances, realized gain/loss on payment
- **Depreciation Agent**: monthly run for laptops, furniture, office equipment
- **Amortization Agent**: monthly run for LMS prepaid + Tuitional AI capitalized dev costs
- **Sanctions Agent**: state machine for request → FA → CFO → approved/rejected; memo journal management; email triggers
- **Reporting Agent**: P&L, BS, Cash Flow, KPIs (EBITDA, ROI, CPL, LTV, CAC, LTV/CAC)
- **Profitability Agent**: per-enrollment, contribution margin + fully-loaded; rolling 12-month LTV
- **Period Close Agent**: T+5 close trigger, reopen with reason, immutability enforcement

**Acceptance criteria:**
- Each agent has its own integration test that runs end-to-end against the smoketest dataset
- Reporting Agent reproduces the Phase 2 smoketest P&L exactly (regression check)
- Penalty math passes the worked example: `(46/60) × 2500 × 0.95 = 1820.83` to 2 dp
- Tuitional AI capitalization correctly carries 24 × AED 2,000 = AED 48,000 on the BS as of feasibility-date-to-now
- A monthly close, run end-to-end, produces a complete report set

**What you must verify:** Run a fictional month with realistic volumes (1000 sessions, 50 enrollments, 10 sanction requests). Inspect the report set. Confirm numbers reconcile.

## Phase 5 — Backend API + CFO Frontend

**Deliverables:**
- FastAPI backend with auth (argon2 + optional TOTP)
- REST endpoints documented via OpenAPI; consumed by frontend
- **CFO Dashboard** (React + Vite + Tailwind):
  - Home: KPI cards, current month P&L snapshot, alerts
  - Reports: P&L, BS, Cash Flow, KPIs — drillable, exportable to PDF/Excel
  - Profitability: per-enrollment table with filters
  - Sub-ledger views: student wallets (with aging), tutor payables, fixed assets, prepaids
  - Manual JE: form with mandatory fields and attachment upload
  - Sanctions: queue view + approve/reject UI
  - Period close: status, close button, reopen with reason
  - FX rates: monthly review and override
- **Department head sanction request form** (lightweight web form, link-shareable)
- **FA / CFO approval click-through pages** (one-time-token URLs from email)
- Responsive: usable on tablet and desktop. Mobile is optional in Phase 5.

**Acceptance criteria:**
- Cypress (or Playwright) e2e tests cover: login, view P&L, post a manual JE, approve a sanction, close a period
- Lighthouse accessibility score ≥ 90 on the dashboard home
- All money displays show currency and 2 dp; AED is default; PKR clearly labeled
- All amounts > AED 100,000 require attachment (per `journal_rules.md`)

**What you must verify:** Click through the entire CFO journey for a fictional month-end close. Confirm UX flows match how you actually work.

## Phase 6 — CI/CD + Observability + Acceptance

**Deliverables:**
- GitHub Actions: lint, type-check, test, security scan on every PR
- Build artifact: Docker images for backend + frontend, plus systemd unit files
- VPS deployment runbook (`infra/deploy.md`): step-by-step Ubuntu 24.04
- Backup script (Postgres logical + physical) with offsite copy hook
- Health check endpoint + minimal Prometheus metrics
- Structured JSON logging with request IDs
- Alert rules: agent failures, ingestion lag, quarantine size, backup age, FX missing
- Final acceptance smoketest: full month run on production-like dataset

**Acceptance criteria:**
- CI green on `main`
- VPS deploy runbook executed by you, full system online
- Backup restored to a fresh DB and ledger reconciles
- Smoketest passes against production-like data

**What you must verify:** Cut over from manual finance work to this system for one month in parallel (shadow mode). Compare numbers. Sign off.

## Out of scope for Phase 1–6

These are tracked as "future" and explicitly not built:

- Churn analysis module (you said: detail later)
- Budgeting / forecasting / sensitivity / seasonality module (you said: detail later)
- Tax engine (UAE VAT, Pakistan WHT)
- Multi-entity / multi-currency consolidation
- Tutor self-service portal
- Department head dashboard (read-only views)
- Mobile app
- Advanced anomaly detection beyond the light-touch defaults

## Working agreement

- **One phase at a time.** No starting Phase N+1 before Phase N is signed off.
- **Red-line not green-light.** Vague "looks good" is not approval; explicit write-up of what was reviewed is required for the audit trail.
- **Spec wins.** If code disagrees with `docs/`, the docs are right and code is wrong. If `docs/` is genuinely wrong, update the docs first, then the code.
- **No silent scope creep.** Anything not in this plan goes into a "deferred" list; we re-scope at end of Phase 6.
