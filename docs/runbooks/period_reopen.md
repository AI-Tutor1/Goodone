# Runbook — Period Reopen

Reopening a closed period is an exception. Auditors look at the count and reasons. Use this runbook to make sure each reopen is justified, scoped, and properly closed back.

## When to use

A closed period needs reopening because:
- A material misstatement was discovered (e.g., a tutor cost was missed, an entry was posted to the wrong account)
- An auditor requires an adjustment
- A late-arriving invoice or transaction belongs to the closed period

**Not a valid reason:** convenience. If a small error is non-material, post a correcting JE in the *current* open period with appropriate narration. Reopen only for material or required corrections.

## Steps

1. **Document the reason** before opening the system. Write 2–3 sentences in your notes:
   - What error was found?
   - How was it discovered?
   - Why is it material enough to reopen?
   - What's the proposed fix?

2. **Dashboard → Period → [closed period]**. Click "Reopen". A dialog requires:
   - Reason text (≥ 30 chars; paste the documented reason)
   - Optional attachment (audit memo, supporting doc)
   - Confirmation

3. **The system flips status to REOPENED.** This is logged with `reopened_at` and `reopened_by`.

4. **Make the corrections.** Post the correcting JE(s). Use clear narration referencing the reason for reopen.
   - If reversing an existing JE: use the "Reverse JE" action on the original. This creates a new JE with mirror-image lines and a reference back. Then post the correct JE.
   - If adding a missed entry: post normally with appropriate date inside the reopened period.

5. **Re-run any affected agents.** If you posted a JE that should have been an automated agent's output, that's fine; the manual entry stands. If you need to re-run depreciation/amortization (e.g., a fixed asset was added late), use Dashboard → Period → Re-run Agents.

6. **Re-run reports preview.** Reports → P&L for the period. Verify the corrected number.

7. **Close the period again.** Dashboard → Period → Close. Same checks as a normal close apply.

8. **Notify stakeholders.** If reports were already distributed, send the corrected reports with a note explaining the change.

## What gets recorded

- `period_close_log` keeps every reopen → re-close cycle
- All reports generated during the previous close are flagged `superseded`
- The new close generates fresh reports with a version number incrementing

## What auditors will see

- Count of reopens per period
- Reason text for each reopen
- The specific JEs added/reversed during the reopen
- Reports clearly versioned

A clean year has zero reopens. One per year is acceptable. Multiple per period is a control quality issue.

## Edge cases

### "I need to reopen a period from 6 months ago"

Allowed but unusual. Comparative figures in subsequent reports will change. The system regenerates them automatically. Brief the audit committee.

### "I reopened, made corrections, and now another sub-ledger doesn't reconcile"

The close checks will fail re-close. Investigate: usually means the correction touched an account but didn't update the sub-ledger because it was a manual JE without sub-ledger keys. Reverse the manual JE and post a proper one with the sub-ledger keys (e.g., for a wallet correction, the JE on `2050` must include `student_id`).

### "I want to reopen but can't see the button"

Only CFO role can reopen. If you have CFO role and don't see the button, the period is already in IN_CLOSING (not yet closed). Clear the close checks first.

### "I reopened in error and want to revert"

Just close again with no changes. The reopen log will show `reopened_at`/`reclosed_at` close together with reason "reopened in error" — perfectly fine.

## Cross-period implications

If the reopen affects a period whose closing balances feed into a later closed period (e.g., a Q1 reopen affects opening balances of Q2), the system flags this. You will need to reopen Q2 too, re-close Q1, then re-close Q2. The system warns you up-front so you can plan the cascade.
