# Smoketests

The smoketest is the system's final acceptance gate at every phase. It runs a fixed, scripted scenario end-to-end and asserts that the resulting books match a committed golden file. If the smoketest passes, the basics work. If it fails, no PR merges.

## 1. The Golden Scenario

A 30-day fictional Tuitional ledger covering April 2026. Sized small enough to inspect by hand but realistic enough to exercise every accounting rule.

**Population:**

- 50 students with names like `S001`–`S050`
- 20 tutors split: `T01`–`T18` paid in PKR, `T19`–`T20` paid in AED
- 100 enrollments distributed across the 50 students
- 8 subjects × 4 grades × 2 curricula in the rate tables

**Opening balances (1 April 2026):**

- 1010 Cash AED: 250,000.00
- 1020 Cash PKR: 0
- 1051 Prepaid LMS License: 7,500.00 (6 months remaining of 12-month prepayment)
- 1111 Laptops Cost: 15,000.00 / 1112 Accum Dep: 15,000.00 (fully depreciated)
- 1113 Furniture Cost: 17,500.00 / 1114 Accum Dep: 10,500.00 (60% depreciated)
- 1121 Tuitional AI Software in Development: 46,000.00 (23 months × 2,000)
- 2050 Deferred Revenue Student Wallets: 95,000.00 (sub-ledger seeded per-student)
- 2020 Tutor Payable PKR: 18,500.00 AED equivalent (March accruals owed; pay 10 April)
- 3010 Share Capital: 100,000.00
- 3020 Retained Earnings: 82,500.00 (computed plug)

Trial balance must equal zero — verified at fixture load.

**Events during April:**

| # | Day | Event | Volume |
|---|---|---|---|
| 1 | 1 | March payroll paid (settle 2020) | 1 batch, 18 tutors |
| 2 | 2–28 | Student wallet top-ups | 60 events |
| 3 | 2–28 | Sessions ingested from "LMS" | 1500 sessions |
| 4 | 2–28 | Sessions resolve to: conducted ≥52 (1100), conducted <52 (150), student-absent (120), teacher-absent (80), cancelled (50) | (totals add to 1500) |
| 5 | 5 | Wallet refunds | 2 events |
| 6 | 8 | Sanction request submitted (marketing dept, AED 30,000) | 1 |
| 7 | 9 | FA approves sanction | 1 |
| 8 | 10 | CFO approves sanction → memo posts | 1 |
| 9 | 12 | Marketing actually spends AED 22,000 against sanction | 1 |
| 10 | 15 | Salary payments to permanent staff | 8 employees |
| 11 | 15 | Counselor + tech + marketing + HR + finance + ops salaries | 1 batch JE |
| 12 | 18 | Ad spend ingested from Sheets | 30 rows, total AED 18,000 |
| 13 | 20 | LMS prepaid amortization (mid-month, captured at close) | — |
| 14 | 22 | One office equipment purchase < threshold AED 800 → expensed | 1 |
| 15 | 25 | Manual JE by CFO: bonus accrual AED 12,000 | 1 |
| 16 | 30 | Month-end automated runs | depreciation, amortization, FX revaluation, AI capitalization |
| 17 | 30 | Period close T+5 (i.e., 7 May in real calendar; for the smoketest fast-forward) | — |

**Tutor compensation in scenario:**

- 1100 conducted ≥52: full pay (mix of AED 1500–3000 rates)
- 150 conducted <52: penalty applies; smoketest includes the canonical 46-min/60-min/AED 2500 example as session #847 — golden file checks that exact JE has lines `Dr 5010 1916.67`, `Cr 2020 1820.83 (PKR equivalent)`, `Cr 5020 95.83`
- 120 student-absent: revenue recognized to 4020, no tutor cost
- 200 (teacher-absent + cancelled): no GL impact

**FX rates in scenario:**

- Stable through April with deliberate small drift: 1 AED = 75.50 PKR on 1 April, 76.20 on 30 April (roughly 1% appreciation of PKR)
- Daily rates seeded; month-end closing rate = 76.20; monthly average = 75.85

**Tuitional AI capitalization:** April adds AED 2,000 → balance 48,000 at end of April.

## 2. Expected outputs (golden files)

Committed at `tests/fixtures/smoketest/golden/`:

- `pnl_april_2026.json` — exact P&L line by line
- `bs_30_april_2026.json` — exact BS
- `cash_flow_april_2026.json` — cash flow indirect method
- `kpis_april_2026.json` — EBITDA, gross margin, etc. (numeric)
- `tutor_payable_30_april_2026.json` — open payables per tutor
- `wallet_aging_30_april_2026.json` — wallet aging summary
- `sanction_memo_balance.json` — open sanction commitments
- `journal_entry_count.json` — total JEs and lines

**Spot-checks the golden file enforces** (fail loudly on these specifically):

1. Session #847 (the penalty example) produces the documented JE byte-for-byte.
2. Total revenue 4010 + 4020 reconciles to wallet decrement on 2050.
3. Sub-ledger sum on 2050 = GL balance on 2050.
4. FX unrealized JE at month-end has a corresponding reversing JE dated 1 May 2026.
5. Tuitional AI 1121 balance is exactly AED 48,000.
6. Sanction memo: 2060 balance = 30,000 − 22,000 = 8,000 (the unspent portion).
7. Period close log has one entry for April 2026, status CLOSED.

## 3. Running the smoketest

```bash
make smoketest
```

This:
1. Spins up a clean Postgres in Docker
2. Runs migrations
3. Loads opening balances
4. Replays the 17-step event script in order
5. Triggers period close
6. Computes all reports
7. Diffs against golden files
8. Reports pass/fail per check

A failed smoketest is non-mergeable. Every diff must be either a fix or a deliberate, reviewed update to the golden file.

## 4. Updating golden files

When a deliberate change to behavior occurs (e.g., a new rule, a fixed bug), the golden files must be updated:

```bash
make smoketest-update-golden
```

This regenerates the golden files from the current run. The diff in the PR shows exactly what changed in the books. CFO/CTO review the diff before approving.

## 5. Acceptance smoketest (Phase 6)

A larger version of the smoketest runs at Phase 6 acceptance, using production-realistic volumes (50,000 sessions, 500 tutors, 5,000 students, 12 months). This validates performance and edge cases at scale. Performance budget per Section 7 of `test_plan.md`.

## 6. Why a fixed scenario rather than random data

A property-based / fuzz approach is great at finding bugs but bad at giving auditors confidence. The smoketest scenario is **inspectable**: a CFO or auditor can read the script, expect a P&L, and verify it. It's the document that proves "yes, the system does what we said."

Property-based tests run alongside the smoketest, but the smoketest is what we point to in audits.

## 7. Phase 2 partial smoketest

Phase 2 ships a subset: opening balances, top-ups, conducted sessions, wallet refunds, period close, P&L generation. The full 17-step scenario above is realized in Phase 4. Phase 2's golden files are a subset of the eventual full set.
