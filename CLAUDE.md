# CLAUDE.md

Context file for Claude Code (and any other LLM agent operating on this repo). Read this before suggesting changes.

## What this repo is

The autonomous finance department for Tuitional Education. Single legal entity (UAE), AED functional currency, online tutoring business, ~50,000 students, ~500 tutors. Tutors are independent contractors paid in PKR.

Currently in **Phase 1** — foundation documentation only. No application code yet. Phases 2–6 build out the system per `docs/plan.md`.

## Critical reading order

When starting a new task, read in this order:

1. `docs/context.md` — what Tuitional does, glossary, business model
2. `docs/architecture.md` — system layers and component responsibilities
3. `docs/chart_of_accounts.yaml` — the source of truth for the GL
4. `docs/accounting_rules.md` — every event → journal mapping
5. The relevant rule file in `docs/rules/`
6. The relevant runbook in `docs/runbooks/`

## Hard rules

These are non-negotiable. If a request asks you to violate one of them, push back.

1. **Determinism in the calculation core.** Python ledger code must be pure, deterministic, and floating-point-free (use `Decimal`). LLMs are never in the journal-posting path.
2. **Append-only ledger.** Posted journals are never edited or deleted. Reversals only.
3. **Double-entry.** Every JE has Dr = Cr to the cent. Database constraint enforces this.
4. **Period immutability.** After period close, no postings to that period. CFO reopen with reason is the only escape hatch.
5. **Sub-ledger reconciliation.** Control accounts always equal their sub-ledger sums. Any code path that updates one without the other is wrong.
6. **The YAML wins.** `docs/chart_of_accounts.yaml` is the source of truth. Code reads it; if they disagree, the YAML is right.
7. **No silent data absorption.** Bad ingestion rows go to quarantine, never dropped, never auto-corrected.

## Workflow conventions

- **Context → Spec → Plan → Implement.** For any non-trivial task: gather context, write a spec, plan steps, then implement. Do not skip to implement.
- **One phase at a time.** Don't write Phase 4 code in a Phase 2 PR.
- **Tests come with code, not after.** A new function ships with its unit test in the same PR.
- **Spec changes are PRs.** If the rules need to change, update `docs/` first, get approval, then update code.

## Code style

- Python 3.11+, fully type-annotated, mypy strict
- `ruff` for lint + format
- `Decimal` for all money; never `float`
- SQLAlchemy 2.x ORM; raw SQL only when necessary, always parameterized
- Pydantic v2 for data validation at boundaries
- Tests with `pytest`, property-based with `hypothesis`
- Imports: stdlib, third-party, local — separated, sorted

## Frontend conventions

- TypeScript strict, React 18, functional components only
- Tailwind for styling; no CSS-in-JS
- TanStack Query for server state; no Redux
- React Hook Form + Zod for forms
- Generate API types from OpenAPI (`openapi-typescript`)

## What you should NOT do without asking

- Add new Python or JS dependencies
- Change the chart of accounts
- Add a new account code or modify an existing one
- Change a posting rule in `docs/accounting_rules.md`
- Modify period-close logic
- Touch the audit log

## What you can do freely

- Refactor for clarity within a module
- Add tests
- Improve docstrings
- Fix obvious bugs (with a test that reproduces the bug)
- Improve frontend layouts within the existing design system

## Current scope boundaries

In scope (Phases 1–6):
- General ledger, sub-ledgers, period close
- Revenue, payroll, FX, depreciation, amortization
- Sanction workflow
- CFO dashboard

Out of scope (do not implement, even if asked unless it's been re-scoped):
- Tax engine
- Multi-entity / multi-currency consolidation
- Tutor portal, student portal
- Churn analysis module
- Budgeting / forecasting
- Mobile apps

If a request lands outside scope, say so and ask whether to add it to the deferred list.

## Tools and slash commands (when used with Claude Code)

This repo is set up to work with the `wshobson/agents` Claude Code plugin set:
- `/conductor` for the Context→Spec→Plan→Implement flow on bigger tasks
- `/python-development` for Python-specific work
- `/backend-development` for FastAPI work
- `/data-engineering` for ingestion adapters
- `/unit-testing` for test work
- `/comprehensive-review` before merging
- `/security-scanning` on schedule
- `/observability` for logging/metrics work

## Personas

The system has one user persona today (CFO). Future personas (FA, dept heads, tutors) are scaffolded in role-based access but disabled. Don't build features for personas other than CFO unless re-scoped.
