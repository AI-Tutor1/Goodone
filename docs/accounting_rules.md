# Accounting Rules

This document maps every business event that the system handles to its journal entry. The Phase 2–4 implementation must produce these journals exactly. Any disagreement between this document and the code is a code bug.

Notation: `Dr` = Debit, `Cr` = Credit. All amounts in AED unless noted.

## 1. Wallet top-up (student adds funds)

**Trigger:** Bank statement adapter sees an incoming payment matching a student top-up record.

**Journal:**
```
Dr 1010 Cash and Bank — AED              [amount]
Cr 2050 Deferred Revenue — Student Wallets    [amount]
  (sub-ledger: student_wallet, student_id = X)
```

**Sub-ledger update:** student wallet balance increases by `amount`.

**Notes:**
- Payment processing fee, if known, is recorded as a separate journal:
  ```
  Dr 5040 Payment Processing Fees   [fee]
  Cr 1010 Cash and Bank — AED            [fee]
  ```
- If the top-up arrives at the bank but the student attribution is unknown, the receipt sits in `1040 Student Top-ups in Transit` until matched.

## 2. Wallet refund

**Trigger:** Student requests refund; CFO authorizes.

**Journal:**
```
Dr 2050 Deferred Revenue — Student Wallets   [amount]
  (sub-ledger: student_wallet, student_id = X)
Cr 1010 Cash and Bank — AED                       [amount]
```

**Notes:** No P&L impact. Reduces both wallet liability and cash by the same amount. Cannot refund more than the current wallet balance — enforced by sub-ledger.

## 3. Session — Conducted (≥ 52 minutes)

**Trigger:** LMS session record arrives with `status = conducted`, `conducted_minutes >= 52`.

**Two journals are posted:**

### 3a. Revenue recognition
```
Dr 2050 Deferred Revenue — Student Wallets       [student_charge]
  (sub-ledger: student_wallet, student_id = X)
Cr 4010 Tutoring Revenue — Conducted Sessions          [student_charge]
  (dimension: enrollment_id = E)
```
Where `student_charge = student_hourly_rate × (scheduled_minutes / 60)`.

### 3b. Cost accrual
```
Dr 5010 Tutor Fees — Base                       [tutor_fee_aed]
  (dimension: enrollment_id = E)
Cr 2020 Tutor Payable — PKR                          [tutor_fee_aed]
  (sub-ledger: tutor_payable, tutor_id = T, original_pkr = X)
```
Where:
- `tutor_fee_aed = tutor_hourly_rate × (scheduled_minutes / 60)` if conducted ≥ 52
- `original_pkr = tutor_fee_aed × (1 / fx_rate_aed_to_pkr_at_session_date)`
  (or however the rate is stored — the sub-ledger holds both AED and PKR amounts; the AED amount is the GL value at accrual)

## 4. Session — Conducted (< 52 minutes; penalty applies)

**Trigger:** As above, but `conducted_minutes < 52`.

**Computation:**
```
prorated   = tutor_hourly_rate × (conducted_minutes / scheduled_minutes)
net_pay    = prorated × 0.95
penalty    = prorated × 0.05    # equivalently: net_pay × (5/95) — same number
```

**Revenue journal:** unchanged. Student is still billed for the full scheduled session (`student_hourly_rate × scheduled_minutes / 60`). Confirm with CFO if student should be partially refunded — current rule is no.

**Cost journals (two parts to keep gross visible):**

### 4a. Gross tutor fee (proration only, no penalty)
```
Dr 5010 Tutor Fees — Base                       [prorated]
Cr 2020 Tutor Payable — PKR                          [net_pay]
Cr 5020 Tutor Fees — Penalty Adjustments             [penalty]
  (dimension: enrollment_id = E, tutor_id = T)
```

This single balanced JE posts the prorated cost, credits the tutor for net pay, and credits the penalty contra account. Net cost on P&L = `5010 + 5020 = net_pay`. Visibility on penalty preserved.

**Worked example:** 46 min on 60 min, AED 2500 rate.
- prorated = 2500 × 46/60 = 1916.67
- net_pay = 1916.67 × 0.95 = 1820.83
- penalty = 1916.67 × 0.05 = 95.83

```
Dr 5010                  1916.67
Cr 2020 Tutor Payable         1820.83
Cr 5020 Penalty Adjust          95.83
```

## 5. Session — Conducted (> 60 minutes; tutor stayed late)

**Trigger:** `conducted_minutes > scheduled_minutes`.

**Rule:** Tutor paid only for `scheduled_minutes` (full rate). No overtime.

**Journal:** Identical to §3 (Conducted ≥ 52 case). The extra minutes are not billed and not paid. They are not noted in the GL but should be visible in the operations dashboard.

## 6. Session — Student Absent

**Trigger:** LMS session with `status = student_absent`.

**Revenue journal posted:**
```
Dr 2050 Deferred Revenue — Student Wallets       [student_charge]
Cr 4020 Tutoring Revenue — Student No-Show              [student_charge]
  (dimension: enrollment_id = E)
```

**No tutor cost journal.** This is the no-show margin policy. Tutor is not paid for student absences.

## 7. Session — Teacher Absent

**Trigger:** LMS session with `status = teacher_absent`.

**No journal.** Tracked in HR/quality sub-ledger only (not GL).

## 8. Session — Cancelled or No Show (other)

**Trigger:** `status in (cancelled, no_show)`.

**No journal.** Tracked for ops metrics.

## 9. Tutor payment (10th of the month)

**Trigger:** CFO triggers monthly payment run; bank statement adapter confirms outgoing transfers.

For each tutor with PKR payable:

**Journal:**
```
Dr 2020 Tutor Payable — PKR                  [accrued_aed]
  (sub-ledger: tutor_payable, tutor_id = T)
Cr 1010 Cash and Bank — AED                       [paid_aed]
Cr 7010 FX Gain/Loss — Realized                   [fx_gain]    if rate moved favorably
  ... or ...
Dr 7010 FX Gain/Loss — Realized              [fx_loss]
  with Cr 1010 = paid_aed in that case
```

Where:
- `accrued_aed` = sum of accruals at original transaction-date rates
- `paid_aed` = `pkr_owed / fx_rate_at_payment_date` (i.e., AED actually spent buying PKR)
- `fx_gain_or_loss = accrued_aed − paid_aed`

The journal **must balance** in AED. The PKR side is sub-ledger only.

## 10. Month-end FX revaluation (unrealized)

**Trigger:** Period close T+1 cron.

**Rule:** All open PKR-denominated monetary balances (i.e., `2020 Tutor Payable — PKR` and `1020 Cash and Bank — PKR` if used) are revalued from their booked AED to the closing rate AED.

**Journal:** for each control account, one aggregate JE:
```
Dr/Cr 2020 Tutor Payable — PKR                  [delta]
Cr/Dr 7020 FX Gain/Loss — Unrealized            [delta]
```

Sign convention: if revalued AED > booked AED (PKR strengthened against AED), liability has grown → debit 7020 (loss).

**Reversal:** On the first day of the next period, the unrealized JE is reversed. This way, when the realized JE posts on settlement, it captures the full FX move from accrual to payment without double-counting.

## 11. Monthly depreciation

**Trigger:** Period close T+1 cron.

**Rule:** For each fixed asset where `purchase_date <= period_end` and `purchase_date + useful_life > period_end`:

```
monthly_dep = cost / useful_life_months
```

**Journal (one aggregate per asset class per month):**
```
Dr 6510 Depreciation — Laptops                 [sum_laptops_monthly_dep]
Cr 1112 Laptops — Accumulated Depreciation         [sum_laptops_monthly_dep]
```

Same pattern for Furniture (6520 / 1114), Office Equipment (6530 / 1116).

The sub-ledger updates each asset's accumulated depreciation individually.

## 12. Monthly amortization

**Trigger:** Period close T+1 cron.

### 12a. LMS prepaid
```
monthly_amort = total_cost / total_months    # 15000 / 12 = 1250 for the LMS license
```
```
Dr 6310 LMS License Amortization              [monthly_amort]
Cr 1051 Prepaid LMS License                        [monthly_amort]
```

### 12b. Tuitional AI capitalization (pre-launch)
While Tuitional AI is `Software in Development`:

```
Dr 1121 Tuitional AI — Software in Development    [capitalized_amount]
Cr 6120 Salaries — Tech                                [capitalized_amount]
```

This is a **reclassification**, not a new expense. The dev salary was already debited to 6120 when paid; this entry moves the capitalizable portion (50% of one developer = AED 2,000/month) out of P&L and onto the BS as an intangible.

### 12c. Tuitional AI amortization (post-launch)
On launch:
```
Dr 1122 Tuitional AI — Software (Launched)    [carrying_value]
Cr 1121 Tuitional AI — Software in Development     [carrying_value]
```

Then monthly:
```
Dr 6540 Amortization — Software               [carrying_value / 60]
Cr 1123 Software — Accumulated Amortization        [carrying_value / 60]
```

## 13. Sanction request — approved

**Trigger:** Both FA and CFO have clicked Approve.

**Journal (memo, paired-account model):**
```
Dr 2060 Sanctioned but Unspent Budget          [amount]
  (sub-ledger: sanction_memo, request_id = R, side: COMMIT)
Cr 9010 Sanction Memo — Counter                     [amount]
  (sub-ledger: sanction_memo, request_id = R, side: CONTRA)
```

**Implementation note (Phase 2 design):** Memo postings use a *paired account* model. The liability-shaped 2060 carries the running commitment with full sub-ledger detail; it is paired with the off-statement counter account 9010 (`is_memo: true`, `subtype: memo`). The JE is balanced (Dr=Cr) without violating the "an account never appears on both sides of one journal" convention. The Reporting Agent excludes the entire 9xxx range from BS and IS roll-ups, so sanction commitments do not appear as a real liability or asset on external statements; they appear only in management reports and in the memo schedule appendix.

The earlier proposal (Dr 2060 / Cr 2060 on the same JE, distinguished only by a sub-ledger `side` field) is **superseded**: it broke a posting convention auditors expect, and added complexity to the GL detail view.

The sub-ledger `sanction_memo` records: request_id, amount, department, requester, approval timestamps, side (`COMMIT | CONTRA | SPEND_REVERSE`). Open commitment per request = `SUM(COMMIT) − SUM(SPEND_REVERSE)`. Reports group by department.

## 14. Spend against an approved sanction

**Trigger:** Actual invoice paid that references an approved sanction.

**Two journals (one balanced JE for the memo reversal, one for the cash/expense):**

### 14a. Reverse the memo (partial or full)
```
Dr 9010 Sanction Memo — Counter                [amount_spent]
  (sub-ledger: sanction_memo, request_id = R, side: SPEND_REVERSE)
Cr 2060 Sanctioned but Unspent Budget               [amount_spent]
  (sub-ledger: sanction_memo, request_id = R, side: SPEND_REVERSE)
```

This is the exact reverse of the §13 pair, scoped to the actual spent amount.

### 14b. Post the actual spend
```
Dr 6XXX (relevant expense)                    [amount_spent]
Cr 1010 Cash and Bank — AED  (or Cr 2010 if not yet paid)   [amount_spent]
```

If actual spend < sanctioned: the unused portion stays in 2060 (still committed) until the request is closed (manual action by CFO; closes via a final SPEND_REVERSE-style entry for the residual).

If actual spend > sanctioned: the engine flags this for CFO; it does not auto-create a new sanction.

## 15. CFO manual journal entry

**Trigger:** CFO posts a JE through the dashboard.

**Mandatory fields:**
- `date` (must be in an open or reopened period)
- `lines` (≥ 2; sum debits = sum credits)
- `narration` (free text, ≥ 10 chars)
- `attachment_url` (per §17 attachment policy)
- `attachment_required` (computed; see §17)
- `attachment_override_reason` (required if `attachment_required` is true and `attachment_url` is null at posting; ≥ 30 chars)
- `posted_by` (user ID; auto-captured)
- `posted_at` (auto-captured)

**The engine validates and posts.** No alteration after posting; reversals only via a new JE that explicitly references the original.

## 16. Period close

**Trigger:** T+5 cron, or CFO clicks "Close period" on the dashboard.

**Steps:**
1. Run all month-end agents (depreciation, amortization, FX revaluation) if not already run.
2. Reconcile each sub-ledger to its control account. **Hard fail if any discrepancy.**
3. Lock the period in `period_close_log`.
4. From now on, the engine rejects any JE with `date` in this period.

**Reopen (CFO only):**
- Records reason in `period_close_log.reopen_reason`
- Auditors will look at this — it should be exceptional, not routine

## 17. Attachment policy (manual JEs > AED 50,000)

Manual JEs whose absolute total exceeds **AED 50,000** require a supporting attachment. The policy is enforced at two stages:

**At posting (soft warn + override):**
1. The engine computes `attachment_required = (source LIKE 'manual:%' AND total_aed > 50000)`.
2. If `attachment_required` is true and `attachment_url` is null:
   - The CFO is prompted to upload before submit.
   - If the CFO chooses to post anyway (e.g., attachment will follow shortly), an `attachment_override_reason` (≥ 30 chars) is required.
   - The override is logged to `audit_log` with `tag = 'WARNING:LARGE_NO_ATTACHMENT'`.
   - The JE posts.
3. If `attachment_url` is provided, the JE posts normally.

**At period close (hard block):**
1. Period close runs `SELECT je_id FROM journal_entries WHERE period = $P AND attachment_required AND attachment_url IS NULL`.
2. If any rows: close is **blocked** with the list of offending je_ids surfaced to the CFO.
3. The CFO must either upload the attachments (an UPDATE on `journal_entries.attachment_url` is permitted *only* for filling a missing attachment, never for replacement; the audit_log records the upload) or document with a final override.

**Implementation columns on `journal_entries`:**
- `attachment_required BOOLEAN NOT NULL DEFAULT false` (set by engine at post time)
- `attachment_url TEXT NULL`
- `attachment_override_reason TEXT NULL`
- Constraint: `(NOT attachment_required) OR (attachment_url IS NOT NULL) OR (attachment_override_reason IS NOT NULL)`.

This pattern keeps day-to-day workflow fluid (CFO can post fast and attach later) while making period close the absolute gate, satisfying the audit trail.

## 18. Year-end close

**Trigger:** T+5 of January (or fiscal year-end).

**Additional step:** Close `3030 Current Year Earnings` to `3020 Retained Earnings`. Computed automatically.

## 19. What this document does NOT cover (yet)

- **Bank reconciliation** (matching `bank_transactions` to system journals) — covered separately in Phase 3 ingestion docs
- **Refund of overpayment to tutor** (rare; treat as reverse of §9)
- **Bad debt write-off** on AR (none currently)
- **Inventory** (none — service business)
- **Lease accounting under IFRS 16** (out of scope; rent is expensed)

## Test obligations

Every rule above must have at least one unit test in Phase 2 that:
1. Constructs the input event
2. Asks the relevant agent to draft the journal
3. Asserts the journal lines exactly match (account, debit, credit, sub-ledger keys)
4. Asks the ledger engine to post it
5. Asserts the new account balances and sub-ledger balances are correct

The smoketest in Phase 2 must run a 30-day scenario covering at least: top-up, refund, conducted (full), conducted (penalty), student-absent, teacher-absent, cancelled, tutor payment, depreciation run, amortization run, FX revaluation, sanction approval, sanction spend, manual JE, period close.
