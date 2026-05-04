# Runbook — Month-End Close

This is the operational checklist the CFO follows for monthly close. Time budget: 5 working days from period-end.

## When to use

Every month, starting on the first business day after month-end (T+1). Close completes by T+5.

## Pre-close (T+1)

1. **Verify automated agents ran overnight.** Dashboard → Period → April 2026 (or whichever) → "Close Readiness". Each of these should be ✓:
   - Depreciation run completed
   - Amortization run completed (LMS, intangibles)
   - Tuitional AI capitalization (if pre-launch) completed
   - FX revaluation completed
   - All sub-ledger reconciliations green
2. **If any agent failed:** check `audit_log` for the error, fix the underlying issue, click "Re-run" on that agent. Common causes: missing rate, missing master data, transient DB issue.
3. **Confirm month-end FX rate.** Dashboard → Master → FX Rates → highlight the closing date. Auto-pulled rate is shown; you can override. Click Confirm.
4. **Quarantine review.** Dashboard → Ingestion → Quarantine. Each open item touching this period must be resolved before close (reprocess, drop with reason, or post a manual JE).

## Manual review (T+1 to T+4)

5. **Read the draft P&L.** Dashboard → Reports → P&L → Period: this month. Look for:
   - Revenue close to expectations
   - Tutor cost ratio in normal range (typically 50–60% of revenue based on prior data; investigate outside ±5%)
   - Any large unexpected G&A items
6. **Read the draft Balance Sheet.** Look for:
   - Wallet liability change reasonable
   - Tutor payable matches what you're about to pay on the 10th of next month
   - Cash matches bank statement
7. **Bank reconciliation.** Dashboard → Sub-ledgers → Bank → upload latest statement → review unmatched items. Match or post manual JEs as needed.
8. **Outstanding sanctions.** Dashboard → Sanctions → ensure no requests are stuck pending CFO from prior periods.
9. **Manual JEs.** Post any accruals, reclassifications, corrections needed before close. Common ones:
   - Salary accrual if payroll runs after month-end
   - Bonus accruals
   - Bank charges not yet swept
   - Reclassifications between accounts

## Close action (T+5)

10. **Final readiness check.** Dashboard → Period → click "Run Close Checks". All must be green.
11. **Click Close Period.** Confirms with a dialog showing the final reports preview.
12. **Wait for completion.** ~30 seconds. Status flips to CLOSED.
13. **Verify reports.** P&L, BS, Cash Flow, KPIs, Profitability, Tutor Payable schedule, Wallet Aging — all generated. Email landed in CFO inbox with PDFs attached.
14. **Distribute reports** as appropriate (board, investors, auditors).

## Troubleshooting

### "Sub-ledger does not reconcile to GL"

- Dashboard → Period → Close Checks → click the failing check for detail
- Will show: account, GL balance, sub-ledger sum, difference
- This is rare; means a posting bypassed sub-ledger update (system bug). Do not force close.
- File a bug. CFO can post a one-time correction JE if necessary, then re-run the check.

### "Quarantine items touching this period"

- Click into Quarantine, resolve each. Drop-with-reason is acceptable for data that genuinely shouldn't be ingested. Reprocess after fixing the upstream issue.

### "FX rate not confirmed"

- Master → FX Rates → confirm the closing date rate. Click Confirm.

### "An automated agent failed"

- Most common: a missing tutor rate for a session. Fix the rate in master data, re-run the agent.
- Less common: DB connection issue. Re-run; if persistent, check logs and infra.

### "I closed the period but realized I missed something"

- Use the period reopen runbook (`runbooks/period_reopen.md`).

## Cadence and notifications

- T+1: automated email "Period close started for [month]"
- T+3: automated reminder if not yet closed
- T+5: automated email "Period auto-closing today" if still open; auto-close fires at end of business
- After close: automated email with reports attached

## Records

Each close generates an entry in `period_close_log` with:
- `closed_at`, `closed_by`
- Snapshot of trial balance and sub-ledger balances
- Hash of the COA version active at close

This snapshot is what auditors will inspect. Do not modify after close.
