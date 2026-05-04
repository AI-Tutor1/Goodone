# Architecture

## 1. Design principles

These constrain every decision below.

1. **Determinism first.** Financial calculations are plain Python with explicit rules. No LLM is in the journal-posting path. Run the system twice on the same inputs, get identical outputs.
2. **Double-entry, always balanced.** Every journal entry has equal debits and credits. Enforced at the database level, not just code.
3. **Append-only ledger.** Posted journals are never edited. Reversals and corrections are new entries that reference the original. Full audit trail by construction.
4. **Source-of-truth separation.** The `chart_of_accounts.yaml` is the spec. Code consumes it. If they disagree, the YAML wins and the code is wrong.
5. **Sub-ledgers reconcile to the GL.** Student wallets, tutor payables, fixed assets, and prepaid schedules are all sub-ledgers. Each must reconcile to its GL control account at every period close.
6. **Period close is real.** After T+5, prior-period data is immutable except via CFO-authorized reopen with logged reason.
7. **LLMs at the edges only.** Used for CFO chat, narrative generation, anomaly explanations. Never for computation.

## 2. Layered architecture

```
                                ┌──────────────────────────────────────────┐
                                │                CFO (UI user)             │
                                └──────────────────────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 5 — HUMAN INTERFACES                                              │
│  • React CFO Dashboard (Vite + Tailwind)                                 │
│  • Sanction request web form (department heads)                          │
│  • Email-triggered approval click-through (FA, CFO)                      │
│  • CFO chat agent (LLM, read-only on the ledger)                         │
└─────────────────────────────────────────────────────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 4 — DOMAIN AGENTS / SERVICES (deterministic Python)               │
│  • Payroll Agent      • Revenue Agent       • FX Agent                   │
│  • Reporting Agent    • Profitability Agent • Sanctions Agent            │
│  • Period Close Agent • Depreciation/Amortization Agent                  │
│  Each is a scheduled job + an HTTP endpoint. No agent ever writes        │
│  directly to the GL — it produces journal entries that the Ledger        │
│  Engine validates and posts.                                             │
└─────────────────────────────────────────────────────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 3 — LEDGER ENGINE                                                 │
│  • Posting service (validates Dr=Cr, account exists, period open)        │
│  • Sub-ledger registries (students, tutors, fixed assets, prepaids)      │
│  • Period close service                                                  │
│  • COA registry (loaded from chart_of_accounts.yaml)                     │
│  This is the only thing that writes to journal_entries / journal_lines.  │
└─────────────────────────────────────────────────────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 2 — INGESTION & VALIDATION                                        │
│  • LMS adapter (sessions, enrollments)                                   │
│  • Google Sheets adapter (ad spend, leads, manual entries)               │
│  • Bank statement parser (CSV)                                           │
│  • FX rate puller (exchangerate.host + manual override)                  │
│  • Manual upload (screenshots, attachments) — month 1 payroll, etc.      │
│  • Validation: rule-based; bad rows go to data_quality_quarantine        │
└─────────────────────────────────────────────────────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 1 — DATA STORE                                                    │
│  • PostgreSQL 16: master data, transactions, GL, sub-ledgers, audit      │
│  • Object storage (filesystem or S3-compatible) for attachments          │
└─────────────────────────────────────────────────────────────────────────┘
```

## 3. Data flow examples

### 3.1 A session is conducted

1. **LMS adapter** polls (or receives webhook from) the LMS hourly. New session record arrives: `enrollment_id`, `scheduled_minutes=60`, `conducted_minutes=58`, `status=conducted`.
2. **Validation** runs: enrollment exists and is active; conducted_minutes is non-negative and ≤ scheduled+30; status is one of the five allowed values. Row passes.
3. **Revenue Agent** picks it up. Computes hourly charge from `student_hour_rates`. Drafts journal: `Dr 2050 Deferred Revenue / Cr 4010 Tutoring Revenue` for the session amount, scoped to `enrollment_id`.
4. **Payroll Agent** picks the same session up. Fetches tutor rate. Conducted >= 52 → no penalty. Drafts: `Dr 5010 Tutor Fees - Base / Cr 2020 Tutor Payable - PKR` for the AED-equivalent amount at the day's FX rate.
5. **Ledger Engine** receives both drafts, validates, posts to `journal_entries` and `journal_lines`. Updates sub-ledgers: student wallet decremented, tutor payable incremented.
6. **Audit log** records: who/what/when (in this case, "system: revenue_agent v1.2.3").

### 3.2 A tutor is paid on the 10th

1. CFO triggers payroll run for prior month. **Payroll Agent** assembles the payable schedule by tutor, totaling PKR amounts owed.
2. CFO confirms; Bank statement adapter ingests outgoing transfers post-fact.
3. For each tutor, **FX Agent** computes realized FX gain/loss = `(rate_at_accrual − rate_at_payment) × pkr_amount`.
4. Posting: `Dr 2020 Tutor Payable - PKR / Cr 1010 Cash AED` for the AED actually paid, plus `Dr/Cr 7010 FX Gain/Loss - Realized` for the difference.

### 3.3 Month-end close

1. Day T+1: cron triggers automated steps — depreciation run, amortization run (LMS prepaid, Tuitional AI), FX revaluation of open PKR payables, prepaid roll-forward.
2. **Reporting Agent** generates draft P&L, BS, Cash Flow.
3. CFO reviews, posts any manual JEs needed.
4. Day T+5: **Period Close Agent** locks the period. `period_close_log` records who/when.
5. Reports email-delivered + dashboard-ready.

## 4. Component responsibilities

| Component | Reads from | Writes to | Schedule |
|---|---|---|---|
| LMS Adapter | LMS API | `sessions`, `enrollments`, quarantine | Hourly |
| Sheets Adapter | Google Sheets API | `ad_spend`, manual_uploads, quarantine | On-demand + daily |
| Bank Adapter | CSV upload | `bank_transactions`, quarantine | On-demand |
| FX Rate Puller | exchangerate.host | `fx_rates` | Daily 00:30 UTC |
| Revenue Agent | `sessions`, `student_hour_rates` | journal drafts | Triggered by new sessions |
| Payroll Agent | `sessions`, `tutor_hour_rates`, `fx_rates` | journal drafts, `tutor_accruals` | Triggered by new sessions; monthly batch on T+1 |
| FX Agent | `tutor_payable` sub-ledger, `fx_rates` | journal drafts, `tutor_payments` | On payment events; monthly revaluation |
| Depreciation/Amortization Agent | `fixed_assets`, `prepaid_schedule`, `intangible_assets` | journal drafts | Monthly T+1 |
| Reporting Agent | GL + sub-ledgers | report artifacts (PDF, dashboard JSON) | Daily incremental + monthly full |
| Profitability Agent | GL with enrollment dimension, allocation rules | computed views | Daily |
| Sanctions Agent | `sanction_requests` | journal drafts (memo), email triggers | Event-driven |
| Period Close Agent | period status | `period_close_log` | T+5 cron + manual trigger |
| CFO Chat Agent (LLM) | GL (read-only), reports | nothing (read-only) | Per-request |

The **Ledger Engine** is the only thing that writes to `journal_entries` and `journal_lines`. All agents produce *drafts* that the engine validates.

## 5. Trust boundaries and security

- **Secrets** (DB password, LMS API key, FX API key, email provider key) live in environment variables, not in code or config files. `.env.example` documents required keys.
- **Attachments** (sanction request supporting docs, JE supporting docs) go to a configured object store with virus scanning hook. In Phase 1, filesystem with size and mime-type validation.
- **Auth** for the CFO dashboard: session-based, password hashed with argon2, optional TOTP 2FA.
- **API surface** is internal only. Frontend talks to FastAPI on the same VPS or via internal network. No public API in Phase 1–6.
- **Rate limit** on the public-facing approval click-through links (one-time tokens, 7-day TTL).

## 6. Failure modes considered

| Failure | Behavior |
|---|---|
| LMS API down | Adapter retries with exponential backoff; alert if down > 1 hour |
| FX API down | Fall back to last known rate; flag in dashboard; require manual override at month-end |
| Validation finds bad row | Quarantine, alert; never silently absorb |
| Posting service rejects journal (Dr ≠ Cr) | Hard fail; alert; never partial-post |
| Period closed but agent tries to post | Hard reject; manual reopen by CFO required |
| Database backup failure | Alert; CI/CD pipeline checks last successful backup age |
| Email delivery failure | Approval state preserved; CFO sees pending in dashboard |

## 7. Why not multi-agent LLM orchestration

A multi-agent LLM framework (AgentScope, AutoGen, LangGraph) was considered and rejected for the calculation core. Reasons:

- **Determinism is non-negotiable** for journal entries. LLMs introduce non-determinism.
- **Auditability**. Every journal must have a traceable, deterministic origin. "An agent decided" is not auditable.
- **Cost.** A platform with 50k students generates many sessions. Per-session LLM calls are wasteful.
- **Complexity.** The agent orchestration we need (cron + event triggers + validated handoff to a posting service) is plain backend engineering.

LLMs are used for the CFO chat, variance commentary, and anomaly narratives — read-only, narrative-only, never in the posting path. These will use the Anthropic API directly with a thin wrapper, no framework dependency.

## 8. Module → directory map (phase 2 onward)

```
src/
├── ledger/             # COA loader, posting service, journal model, period close, sub-ledger orchestration
│   ├── coa.py          # Loads and queries chart_of_accounts.yaml (canonical Phase 2 path)
│   ├── coa_loader.py   # YAML → DB upsert
│   ├── posting.py
│   ├── period.py
│   └── subledger.py    # Sub-ledger registry; per-sub-ledger logic lives in src/subledgers/
├── subledgers/
│   ├── student_wallet.py
│   ├── tutor_payable.py
│   ├── fixed_assets.py
│   ├── prepaid_schedule.py
│   ├── intangible.py
│   └── sanction_memo.py
├── ingestion/
│   ├── lms.py
│   ├── sheets.py
│   ├── bank.py
│   ├── fx.py
│   └── manual_upload.py
├── validation/         # Rule engine, quarantine
├── agents/
│   ├── revenue.py
│   ├── payroll.py
│   ├── fx.py
│   ├── depreciation.py
│   ├── amortization.py
│   ├── sanctions.py
│   ├── reporting.py
│   ├── profitability.py
│   └── period_close.py
├── api/                # FastAPI routes
├── chat/               # LLM-backed CFO chat (Anthropic API)
├── email/              # Provider abstraction; stubbed in dev
└── core/               # Shared: config, logging, db session, types
```

Tests mirror this structure under `tests/`. Migrations under `migrations/`. Frontend under `frontend/`.
