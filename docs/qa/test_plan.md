# Test Plan

Testing strategy for the Tuitional Finance system. The cost of a finance system bug is much higher than a typical app — wrong numbers in front of an investor, a tutor underpaid, a wallet refunded incorrectly. Tests are the safety net.

## 1. Test pyramid

```
                    ┌────────┐
                    │  E2E   │   ~20 tests, run on PR (mostly Cypress)
                    └────────┘
                  ┌────────────┐
                  │ Integration │   ~80 tests, run on PR
                  └────────────┘
              ┌────────────────────┐
              │       Unit          │   ~500 tests, run on every commit
              └────────────────────┘
            ┌────────────────────────┐
            │     Property-based     │   ledger-engine specific
            └────────────────────────┘
          ┌──────────────────────────┐
          │   Smoketest / Golden     │   end-to-end fixed scenario
          └──────────────────────────┘
```

## 2. Unit tests

**Coverage target:** ≥ 90% on `src/ledger/`, `src/subledgers/`, `src/agents/`. ≥ 80% elsewhere.

**What to unit test:**

- Penalty math (`payroll.compute_payment`) with all edge cases:
  - 60-min full → no proration
  - 52-min → full pay
  - 51-min → prorated × 0.95
  - 30-min → prorated × 0.95
  - 90-min (overtime) → capped at scheduled
  - 0-min (degenerate) → 0
- FX translation (every conversion direction; rounding to 2 dp)
- Wallet operations: top-up, debit, refund, sequence of operations preserves invariant `balance >= 0`
- Tutor payable: accrual + payment + revaluation, AED reconciles to PKR × rate
- Depreciation schedule: monthly amount, last-month rounding, fully-depreciated stop
- Amortization: same as above for prepaids
- Capitalization: pre-launch reclass + post-launch amortization

**Tools:** pytest, pytest-cov, hypothesis

## 3. Property-based tests (ledger engine)

Using `hypothesis`. Properties:

1. **Balance invariant.** Generate any sequence of valid postings → after each, GL trial balance has Dr = Cr.
2. **Sub-ledger reconciliation.** Generate any sequence of postings → GL control balance equals sum of sub-ledger balances at every step.
3. **Idempotency.** Generate any sequence of source events → ingesting twice produces the same end state.
4. **Period immutability.** After period close, no mutation can change closed-period totals.
5. **Reversal correctness.** For any posted JE → reverse it → resulting trial balance unchanged from before posting.

These properties run with thousands of generated cases per test. Failures shrink to minimal counterexamples.

## 4. Integration tests

Each agent has at least one end-to-end test:

- **Revenue Agent:** insert sessions → run agent → verify journals + sub-ledger updates
- **Payroll Agent:** insert sessions → run agent → verify accrual + AED amounts + tutor payable
- **FX Agent:** simulate rate change → run revaluation → verify journal + reversal next period
- **Depreciation Agent:** seed assets → run monthly → verify schedule progression over 12 months
- **Sanctions Agent:** submit → FA approve → CFO approve → spend → close cycle
- **Period Close Agent:** full month-end with all agents → verify reports generate and balance

**Tools:** pytest with a real Postgres (Docker test container), no mocking of the database.

## 5. End-to-end tests (frontend)

**Tool:** Cypress (or Playwright; final choice in Phase 5).

**Scenarios:**

1. CFO logs in, navigates to home, sees current month KPIs.
2. CFO opens P&L, drills into a line, sees the underlying JEs.
3. CFO posts a manual JE (with attachment), it appears in the ledger view.
4. CFO posts an unbalanced JE, sees the form-level error and cannot submit.
5. Department head submits a sanction request via emailed link.
6. FA approves via emailed click-through.
7. CFO approves; memo journal posts; appears in `2060` activity.
8. CFO links an actual spend to the sanction; memo reverses.
9. CFO closes a period (after all checks green).
10. CFO reopens a closed period with a reason.
11. CFO uploads a bank statement; matches reconcile.
12. CFO views per-enrollment profitability and exports to XLSX.

## 6. Smoketest / Golden scenario

A 30-day fictional Tuitional ledger committed as a fixture. Includes:

- 50 students, 20 tutors, 100 enrollments
- 1500 sessions across all five outcome states
- 5 wallet top-ups, 2 wallet refunds
- 3 sanction requests in different states
- 5 manual JEs by CFO
- One month-end FX revaluation
- One depreciation run, one amortization run
- One Tuitional AI capitalization JE

The expected outputs (P&L, BS, KPIs) are committed as JSON golden files. The smoketest:
1. Resets the database
2. Seeds the fixture
3. Runs every agent in proper order
4. Closes the period
5. Generates reports
6. Asserts byte-equality (or numeric equality with `Decimal` tolerance) against the golden files

Any divergence requires either (a) a bug fix or (b) a deliberate update to the golden file with PR review.

## 7. Performance tests

Baseline targets (Phase 6 acceptance):

- Posting 1000 system-generated JEs: < 30 seconds
- Generating monthly P&L: < 5 seconds
- Loading dashboard home (cold): < 2 seconds
- Cypress full suite: < 10 minutes

Tools: locust for API load, lighthouse for frontend.

## 8. Security tests

- **Bandit** (Python) on every CI run
- **npm audit** on frontend deps
- **OWASP ZAP** baseline scan in pre-prod
- Manual review: input validation on all mutating endpoints, file upload mime checks, SQL injection sanity (we use SQLAlchemy ORM, but raw SQL paths get reviewed)
- Auth flow review: session security, CSRF, TOTP enrollment

## 9. Data quality tests

Run nightly on prod data:

- All JEs balance (Dr = Cr)
- All control accounts reconcile to sub-ledgers
- No future-dated entries
- No JEs in closed periods (post-close)
- Wallet balances all ≥ 0
- Tutor payable balances reconcile across currencies

Failures alert immediately.

## 10. CI configuration

GitHub Actions workflow on every PR:

```
on: pull_request
jobs:
  lint:
    - ruff
    - mypy
    - eslint
    - tsc --noEmit
  test:
    - pytest -q --cov (target: 90% on key modules)
    - vitest (frontend unit)
    - cypress run (E2E against test stack)
  security:
    - bandit
    - npm audit
    - safety check
  smoketest:
    - run the golden scenario, assert against fixtures
```

PRs cannot merge with any check failing. The smoketest is the final gate.

## 11. Local developer testing

- `make test` — unit tests
- `make test-int` — integration tests (spins up Docker)
- `make smoketest` — golden scenario
- `make e2e` — Cypress
- `make all` — everything

Pre-commit hook runs lint and unit tests. Slow tests (integration, E2E) are CI-only.

## 12. Test data management

- Unit/integration: factories in `tests/factories/` produce realistic objects
- Smoketest: a hand-curated fixture in `tests/fixtures/smoketest/`
- E2E: a separate seed database with a known set of data
- Sensitive data: never. All test data is fake.

## 13. Acceptance criteria for production cutover

Phase 6 acceptance requires:

- All CI green on `main`
- Smoketest golden files current and approved
- One full month of parallel operation (manual books vs. system) with reconciliation report showing < 0.1% variance
- Backup restore drill executed and ledger reconciles after restore
- Disaster recovery runbook walked through

Only after all of the above does the system become the system of record.
