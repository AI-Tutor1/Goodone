# Chart of Accounts

The machine-readable source of truth is **`chart_of_accounts.yaml`** in this directory. This document explains the structure, conventions, and reasoning. **Read both before approving.**

## Purpose

A chart of accounts is the spine of any general ledger. Every journal entry in the system references an account code from this list. Getting it wrong now means rewriting reports later, which means losing comparability with prior periods. Worth taking time on.

## Numbering convention

Numeric ranges have meaning:

| Range | Meaning | Statement |
|---|---|---|
| 1000–1099 | Current assets | Balance Sheet |
| 1100–1199 | Non-current assets | Balance Sheet |
| 2000–2099 | Current liabilities | Balance Sheet |
| 2100–2199 | Non-current liabilities | Balance Sheet |
| 3000–3099 | Equity | Balance Sheet |
| 4000–4099 | Revenue | Income Statement |
| 5000–5099 | Cost of Service (direct) | Income Statement |
| 6000–6099 | Operating Expenses | Income Statement |
| 7000–7099 | Non-operating items | Income Statement |

## Header vs postable accounts

Some accounts (e.g. `1000 Current Assets`) are **headers** — they exist for reporting hierarchy but you cannot post a journal entry to them directly. They aggregate their children. The YAML has `is_postable: false` for these.

Postable accounts (`is_postable: true`) are the leaves of the tree.

This is enforced by the ledger engine — attempting to post to a non-postable account is rejected.

## Sub-ledgers

Some accounts are GL **control accounts** — their balance must equal the sum of an underlying sub-ledger. The YAML's `sub_ledger` field marks which one:

| Sub-ledger | Control account(s) | What it tracks |
|---|---|---|
| `student_wallet` | 2050 Deferred Revenue — Student Wallets | Per-student running balance, top-ups, consumption, refunds, aging |
| `tutor_payable` | 2020 Tutor Payable — PKR, 2030 Tutor Payable — AED | Per-tutor running balance, accruals, payments |
| `fixed_asset` | 1111/1112, 1113/1114, 1115/1116 | Per-asset register: cost, life, accumulated depreciation, NBV |
| `prepaid` | 1051, 1052 | Per-prepaid: total, schedule, monthly amortization, unamortized balance |
| `intangible` | 1121, 1122, 1123 | Per-intangible asset register, with capitalization log and amortization |
| `sanction_memo` | 2060 | Approved-but-unspent sanctions, per request |

The Phase 2 ledger engine includes a reconciliation routine that fails the period close if any control account disagrees with its sub-ledger sum.

## Why a separate "Student No-Show" revenue line (4020)

This is intentional and worth flagging. When a student is absent, revenue is recognized but no tutor cost is incurred. This is a **margin source** for Tuitional and an explicit policy choice (per `context.md`).

By isolating this revenue on its own line:
- The CFO can see at a glance how much of total revenue depends on this policy.
- A change in policy (e.g., a tutor contract amendment that requires payment for student no-shows) becomes a measurable risk.
- Auditors can review it as a separate population.

If 4020 is < 5% of revenue, it's a footnote. If it's > 15%, it's a strategic dependency.

## Why "Tutor Fees — Penalty Adjustments" (5020) is a contra account

The penalty rule (5% reduction for sub-52-minute classes) reduces tutor cost. We could net this against `5010 Tutor Fees — Base` on posting, but separating it has two benefits:

1. **Visibility** — operations can see total penalty volume. If it spikes, that's a quality signal (tutors cutting sessions short, or LMS time-tracking issues).
2. **Audit clarity** — the gross-up is preserved. Anyone reviewing tutor costs sees the full earned amount and the penalty as a separate adjustment.

For external reporting, 5010 + 5020 collapses to a single Cost of Service line.

## Why FX gain/loss is split (7010 vs 7020)

- **Realized (7010)** — booked when actual cash moves on the 10th of the next month. This is real money won or lost.
- **Unrealized (7020)** — booked at month-end when open PKR payables are revalued at the closing rate. This may reverse next month if rates move back.

Splitting them lets a reader see "real" FX impact (7010) versus "paper" impact (7020). Most analysts treat unrealized FX as noise.

## Why `2060 Sanctioned but Unspent Budget` is on the balance sheet

It is technically a memo account — it doesn't represent a real legal liability. Some companies put it off-balance-sheet entirely. We choose to put it on the BS for two reasons:

1. The double-entry stays clean: when a sanction is approved, the contra entry hits an equity-like memo account (handled by a sub-ledger so it doesn't pollute retained earnings).
2. The CFO sees the total committed-but-unspent figure at a glance.

For external/IFRS-compliant reporting, the BS will show 2060 in a "Memo accounts" section below the equity line, not within liabilities. The Reporting Agent handles this presentation.

## How to change the COA

Adding accounts: edit `chart_of_accounts.yaml`, increment `version`, run the loader migration. Existing journal entries are unaffected.

Renaming accounts: edit `name` field; existing entries continue to reference the same code. No migration of journals needed.

**Removing accounts:** Only allowed if `select count(*) from journal_lines where account_code = X = 0`. The loader checks this and refuses removal otherwise. This prevents accidental loss of history.

**Changing account types or normal balance:** Forbidden after first journal posts. Would require an explicit migration that reverses all related entries — practically, this means "design it correctly upfront."

## Approval

This document and the YAML must be approved by the CFO before Phase 2 begins. Approval = explicit sign-off in writing referencing `version: 1`. Subsequent versions require similar sign-off.
