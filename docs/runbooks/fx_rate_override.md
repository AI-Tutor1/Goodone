# Runbook — FX Rate Override

The system auto-pulls AED/PKR rates daily. Most days that's fine. Sometimes you need to override — month-end, anomaly day, missing data, or a different policy choice.

## When to override

1. **Month-end closing rate.** Best practice: confirm the auto-pulled rate matches a reliable source (central bank, your bank's published rate). If different, override.
2. **API outage day.** If `exchangerate.host` returned no data and the system carried forward the prior rate, you may want a different value for the missing day.
3. **Outlier day.** A spike or drop > 5% from the trailing average is flagged. Decide: was it real (keep auto rate, suppress alert), or stale data (override to a market consensus rate).
4. **Policy bridge.** If you choose a monthly fixed rate for accruals (vs. daily), override every day of the month to the chosen value. Note this is a policy choice that should be documented.

## How to override

1. **Dashboard → Master → FX Rates**.
2. Choose date range. The grid shows date | source (auto/manual) | rate | who/when.
3. Click any row to edit. Modal opens:
   - New rate (Decimal, > 0)
   - Reason (required, ≥ 20 chars)
   - Effective date (defaults to the row's date)
4. Click Save. The override:
   - Stores the new rate with `source: manual`, `set_by: <you>`, `set_at: now()`
   - Logs the prior auto value and the reason
   - Emits an event so the FX Agent picks it up on next run

## Effects

- **Future entries** (those posted *after* your override) use the new rate immediately.
- **Already-posted entries** are not retroactively re-translated. Their accrued AED stays.
- **Month-end revaluation** uses the closing rate as it stands at month-end. If you override the closing rate before the FX Agent has run, the revaluation uses your override. If you override after, you can re-run the FX Agent (Dashboard → Period → Re-run FX) to refresh the unrealized JE.
- **Realized FX** on tutor payment day uses whatever rate is effective on the payment date (which may be a manual override).

## What NOT to do

- **Don't override historical rates that are already used in posted entries.** If a transaction posted on 5 April at rate X, and you change the 5 April rate to Y, the system does not retroactively update that posting. The new rate would only matter if you reposted those entries (which means reopening the period). For a clean override, reopen the period, reverse the affected entries, repost with the new rate.
- **Don't override "to make the numbers look better."** The FX rate reflects market reality. Smoothing it through manual override is a bad practice and audit-flagged.
- **Don't forget the reason.** The system requires it; the auditor reads it.

## Bulk overrides

If you're applying a monthly fixed-rate policy and need to override 30 days at once:

```bash
# CLI helper (Phase 6)
tuitional fx-override --from 2026-04-01 --to 2026-04-30 --rate 75.85 --reason "Monthly fixed-rate policy per CFO memo dated 2026-03-25"
```

The dashboard UI also supports this via "Bulk Override" — date range + single rate + single reason.

## Audit trail

Every override creates a row in the FX rate history table. The pattern shows:

- Original auto rate
- Manual rate
- Reason
- Who/when
- Whether the override was followed by a re-run of the FX Agent

The Reporting Agent can produce an "FX Override Log" report on demand.

## Common scenarios

### "I disagree with the auto-pulled month-end rate"

Confirm against your bank's published rate or central bank. If different by > 0.5%, override. Reason: "Aligned with [source] published rate of [X] for closing valuation."

### "exchangerate.host was down for 3 days; the system carried forward"

Check what each day's true rate was (your bank statement showing actual conversion rates is one source). Override each day. Reason: "API outage 12-14 April; rates set from [source]."

### "I want to use a single monthly rate for all P&L items in the month"

This is the IAS 21 monthly average treatment. The FX Agent already does this for P&L items by default. You don't need to override daily rates — the agent computes the monthly average. Confirm it's set to "monthly average for P&L" in agent config.
