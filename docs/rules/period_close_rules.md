# Period Close Rules

The period close discipline turns "live data" into "frozen reportable history." It is the single most important monthly process — bugs here corrupt comparability across periods.

## 1. The cycle

| Day | Action |
|---|---|
| Last day of month | Period is `OPEN`. All ingestion and posting normal. |
| T+1 (first business day of next month) | **Automated agents run**: depreciation, amortization, FX revaluation. Period status `IN_CLOSING`. New ingestion still allowed but flagged. |
| T+1 to T+5 | CFO reviews drafts, posts manual JEs, approves rates. Status remains `IN_CLOSING`. |
| T+5 (5th business day of next month) | **Period close** triggered. Period transitions to `CLOSED`. New JEs to this period rejected. Reports finalized and emailed. |
| After T+5 | Period is `CLOSED`. Adjustments require CFO reopen. |

Working day convention: skip weekends. Public holidays are configurable (currently AED-region default: Eid, National Day, etc.).

## 2. Pre-close automated steps (T+1)

In order:

1. **FX rate confirmation.** If month-end rate hasn't been confirmed (auto-pulled is fine; manual override optional), prompt CFO. Block close until confirmed.
2. **FX revaluation.** All open PKR monetary balances revalued at closing rate. JEs post to `7020 FX Gain/Loss — Unrealized` with auto-reversal at T+1 of next period (i.e., next period gets a reversing JE on its first day).
3. **Depreciation run.** For each fixed asset where the period is within useful life, post monthly depreciation per `accounting_rules.md` §11.
4. **Amortization run.** Prepaids (LMS license, others) and intangibles (post-launch software). Per `accounting_rules.md` §12.
5. **Tuitional AI capitalization.** If pre-launch, reclassify the month's allocated dev cost from `6120` to `1121`.
6. **Sub-ledger reconciliation.** Each control account vs. its sub-ledger sum. Mismatch → block close, alert CFO.
7. **Quarantine check.** Any quarantine item touching this period → block close.
8. **Bank reconciliation completeness check.** All bank transactions matched or flagged → if any unmatched, soft warning (does not block; CFO acknowledges).

## 3. Pre-close manual steps (T+1 to T+5)

CFO does:

- Review draft P&L and BS (Reporting Agent generates these as drafts).
- Post any manual JEs needed for accruals not auto-captured (e.g., pending bonus accrual, last-minute invoices).
- Approve or override the FX rate.
- Resolve any flagged quarantine items.
- Sign off on the close.

## 4. Closing the period

Triggered by CFO via dashboard "Close period" button OR by T+5 cron auto-close (configurable; default: cron auto-closes if CFO hasn't acted).

On close:

1. Final reconciliation pass. If any check fails: hard error, period stays IN_CLOSING.
2. `period_close_log` row inserted: `(period, closed_at, closed_by, sub_ledger_balances_snapshot, gl_balances_snapshot, summary_metrics)`.
3. Period status flipped to `CLOSED` in `periods` table.
4. Reports auto-generated:
   - Monthly P&L (PDF, XLSX)
   - Monthly BS (PDF, XLSX)
   - Monthly Cash Flow (PDF, XLSX)
   - KPI dashboard snapshot (JSON)
   - Per-enrollment profitability (XLSX)
   - Tutor payable schedule (XLSX, used by ops to actually pay)
5. Reports emailed to CFO and posted to dashboard.

## 5. Post-close immutability

After close:

- INSERT/UPDATE on `journal_entries` or `journal_lines` with `date` in closed period: rejected by DB constraint and engine.
- Sub-ledger updates with `effective_date` in closed period: same.
- Existing rows are immutable.

## 6. Reopen

Only the CFO can reopen a closed period.

Required:
- Reason text (≥ 30 chars)
- Optional attachment

On reopen:
- Period status → `REOPENED`
- `period_close_log.reopen_reason` recorded
- `period_close_log.reopened_by`, `reopened_at` recorded
- All previously generated reports get a `superseded` flag in metadata; new reports issued on next close

After CFO finishes the necessary entries, they re-close the period. The reopen_log retains the full history. A period can be reopened multiple times; each reopen + close is logged.

**Auditor view:** A period that has been reopened is visually flagged in reports with the count and reasons. Frequent reopens are a red flag for control quality.

## 7. Year-end close

Y+5 of the new fiscal year:

- All monthly closes for the year must be complete.
- Additional step: Net of `4000-7999` rolls into `3030 Current Year Earnings`.
- Closing entry: `Dr 3030 / Cr 3020 Retained Earnings` for net profit (or reverse for loss).
- `3030` zeroed at year-end; rebuilds during new year.

This is automated; CFO confirms.

## 8. Auditor pack

At year-end close, the system produces an "auditor pack" zip containing:

- All monthly P&Ls and BSs
- Annual P&L, BS, Cash Flow
- General ledger detail (CSV)
- Journal entries detail (CSV)
- Sub-ledger trial balances at year-end
- Period close log (full history)
- Manual JE attachments
- Sanction request log
- FX rate history
- COA version snapshot

Generated on demand via `tuitional auditor-pack --year YYYY`.

## 9. Hard blocks

Period close is **hard-blocked** if any of:
- Sub-ledger does not reconcile to GL control account
- Open quarantine items touching the period
- Closing FX rate not confirmed
- A manual JE attachment is missing for a JE > AED 50,000 (warning at posting; hard block at close)
- Required automated agent run failed (e.g., depreciation crashed)

Soft warnings (close allowed but flagged):
- Bank transactions unmatched
- Anomalies (duplicate-looking JEs)
- Wallet balances dormant > 12 months (informational)

## 10. Disaster scenarios

If close fails mid-process and leaves the system in a half-closed state:

- The period remains IN_CLOSING.
- The `period_close_log` records the failure with full stack trace.
- CFO can retry the close via dashboard.
- No data corruption occurs because each step is its own atomic transaction.

If a closed period needs full rebuild (e.g., discovery of major systemic error):

- Reopen the period.
- Use `reverse_journal` for entries to be undone.
- Re-run agents as needed.
- Close again.
- The complete history (original entries + reversals + new entries) is preserved. No data is ever deleted.
