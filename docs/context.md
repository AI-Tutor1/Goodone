# Context — Tuitional Finance Domain

This document is required reading for anyone (human or LLM) working on this codebase. It establishes the business model, vocabulary, and domain assumptions that the rest of the docs and the code rely on.

## 1. What Tuitional does

Tuitional Education (`tuitionaledu.com`) is an online 1-on-1 tutoring platform serving the Gulf market, with curriculum coverage of Grades 6–8, IGCSE, GCSE, and A-Levels. Students attend live video sessions with vetted tutors. The company has ~50,000 registered students and 500+ screened tutors as of platform statistics.

There is a second product, **Tuitional AI**, currently in development (going to market within ~30 days from Phase 1 start). It automates checking, grading, and end-to-end student lifecycle management as a SaaS platform. Both products run on the same legal entity.

## 2. Operating model

- **Single legal entity.** UAE-based. Reporting currency: AED.
- **Tutors are independent contractors**, paid in PKR. Most are based in Pakistan.
- **Students pay in AED**, via wallet top-ups (see §3).
- **Staff:** Counselors, permanent teachers (a few hours/month), tech, marketing, HR, finance, operations.
- **Payment cycle:** Tutors are paid on the **10th of the month following** the month worked. April hours → paid 10 May. All employees and contractors are paid on the 10th.

## 3. Wallet model — critical to revenue recognition

Students do not pay per session. They pay upfront to **top up a wallet balance** ("Book amount" in operator language). When they attend a session, the session's hourly charge is **debited from the wallet**, and at that moment revenue is recognized.

Properties:

- Wallet is a **pooled balance** — not earmarked for any tutor or subject.
- Balance is **refundable** at any time on student request.
- Balance has **no expiry**.
- Wallet behaves like a bank account: top up at will, drawdown on consumption.

Accounting consequence: every wallet top-up creates a **liability** on Tuitional's balance sheet (Deferred Revenue / Customer Wallet, account `2050`). Revenue is recognized only on session conduct. See `accounting_rules.md` and `ifrs_treatments.md`.

## 4. Session outcomes — the five states

Every scheduled session resolves into exactly one of five states. The journal entries differ:

| State | Student wallet | Tutor payable | Notes |
|---|---|---|---|
| **Conducted** | Debited (revenue recognized) | Credited (cost accrued) | Normal happy path |
| **Student Absent** | Debited (revenue recognized) | **No credit** | Policy: tutor not paid for student no-show. Margin source. |
| **Teacher Absent** | No transaction | No transaction | Tracked in HR sub-ledger, not GL |
| **Cancelled** | No transaction | No transaction | Tracked for ops metrics |
| **No Show** | No transaction | No transaction | Distinct from above; defined by LMS |

The Student Absent margin is a real and intentional revenue source. It will be reported on a separate P&L line (`4020 Tutoring Revenue — Student No-Show`) so its size and dependency are visible.

## 5. Tutor compensation — penalty rule

If a tutor conducts a class for **less than 52 minutes** of a 60-minute scheduled slot, a penalty applies:

```
payment = (conducted_minutes / scheduled_minutes) × tutor_rate × 0.95
```

Threshold and edge cases:

- `conducted_minutes >= 52` → tutor receives full `tutor_rate` (no proration, no penalty).
- `conducted_minutes < 52` → formula above; the 5% is **multiplicative** (not flat AED, not subtracted from full rate).
- `conducted_minutes > scheduled_minutes` (tutor stays late) → tutor receives `tutor_rate` capped at scheduled (no overtime).
- Worked example: 46-minute conduct on a 60-minute / AED 2500 slot →
  `(46/60) × 2500 × 0.95 = AED 1,820.83` (rounded to 2 dp).

The 5% is applied **after** proration, not before. Order matters for floating-point and tax interpretations.

## 6. Pricing structure — Tutor Hour Management

- **Tutor rates** vary by `(tutor × subject × grade × curriculum)`. Master table: `tutor_hour_rates`. Example: same tutor charges 2500 AED/hr for IGCSE Chemistry Grade 9 but 2750 for Grade 10.
- **Student rates** also modeled as `(subject × grade × curriculum)` in master table `student_hour_rates`. Initial population may be uniform; the table allows tiering without code change.
- Both tables are **effective-dated** (`effective_from`, `effective_to`). Rate changes do not break historical sessions.

## 7. Enrollments

An **enrollment** is the relationship between a student and a tutor for a specific subject/grade/curriculum. Profitability is reported per enrollment as well as per student and per tutor.

- Enrollments have `start_date`, optional `end_date`, status (`active`, `paused`, `churned`).
- Per-enrollment profitability is computed two ways (always reported side-by-side):
  - **Contribution margin** = Revenue − Direct tutor cost − Payment processing fees
  - **Fully-loaded profit** = Contribution margin − allocated overhead − amortized CAC
- Lifespan is computed from first to last conducted session (closed cohorts) or projected (open cohorts).

## 8. Foreign exchange

- **Functional currency:** AED.
- **Tutor payable currency:** PKR.
- **Translation policy** (IFRS, see `ifrs_treatments.md`):
  - P&L items: monthly average AED/PKR rate
  - Monetary balance sheet items (PKR tutor payables): closing rate at period end
  - Realized FX gain/loss: booked when tutors are actually paid (10th of next month)
  - Unrealized FX gain/loss: booked at month-end revaluation of open PKR payables
- **Rate source:** `exchangerate.host` daily auto-pull, with manual override at month-end.

## 9. Fixed assets and intangibles

- **Capitalization threshold:** AED 1,000. Items below threshold are expensed.
- **Depreciation:** Straight-line. Laptops 3 years, furniture 5 years, office equipment 5 years.
- **Existing assets:**
  - 15 laptops × AED 1,000 cost, purchased ~3 years ago → fully depreciated, NBV ≈ 0
  - Furniture (20 chairs × AED 500, 5 tables × AED 1,500) → 60% depreciated, NBV ≈ AED 7,000
- **Tuitional AI capitalization (IAS 38):**
  - Feasibility established May 2024 (24 months prior to Phase 1)
  - 1 developer × AED 4,000/month × 50% allocation = AED 2,000/month capitalizable
  - Cumulative AED 48,000 to be recognized as `Intangible Asset — Software in Development` (account `1121`)
  - On launch (~June 2026), reclassify to `1122 Intangible Asset — Software (Launched)` and amortize straight-line over 5 years (AED ~800/month)
- **LMS license:** AED 15,000/year, paid annually upfront → Prepaid Expense, amortized AED 1,250/month to P&L.

## 10. Approvals and budgets — the sanction workflow

Spend by any department requires sanction:

1. **Department head** raises a request (amount, purpose, supporting attachment).
2. **Financial Analyst (FA)** reviews and decides.
3. **CFO** gives final approval (regardless of amount — no threshold delegation in current setup).
4. On approval, a **memo entry** is recorded in account `2060 Sanctioned but Unspent Budget` (off-balance-sheet commitment tracker).
5. When actual spend occurs, a real journal hits the relevant expense account and clears the memo.
6. Rejections must include a reason, visible to the requester.

Approvals are **email-triggered** with a **click-through web link** for FA/CFO to record the decision. Plain email parsing is rejected as too flaky for audit.

## 11. Period close

- **Cycle:** T+5. Five working days after month-end, the period locks.
- **Reopen:** Only the CFO can reopen a closed period, and the action is logged with reason.
- **After close:** Any adjustment posts as a manual journal entry by CFO with mandatory narration and attachment.

## 12. The CFO

The single user persona for Phase 5. The CFO can:

- View any report, any period, any granularity (per-enrollment, per-tutor, per-department).
- Post manual journal entries (with mandatory metadata).
- Approve or reject sanction requests (after FA).
- Override the FX rate for a period.
- Reopen a closed period (logged).

Tutors, students, department heads, and other roles do **not** have UI access in Phase 5. Role-based access is designed in but disabled.

## 13. Glossary

- **Book amount** — student wallet top-up (operator term)
- **Booked** — funds received but not yet recognized as revenue
- **Conducted minutes** — actual minutes the session ran on the LMS
- **Scheduled minutes** — what the session was booked for (typically 60)
- **Penalty** — the 5% multiplicative reduction below 52 conducted minutes
- **No-show margin** — revenue from student-absent sessions where tutor is not paid
- **Enrollment** — student × tutor × subject × grade × curriculum relationship
- **Sanction** — pre-approved budget commitment (not yet spent)
- **Memo entry** — informational journal in `2060` that does not affect P&L or BS totals
- **CAC** — Customer Acquisition Cost, amortized over enrollment realized lifespan
- **LTV** — Lifetime Value, computed at enrollment and student level
- **EBITDA** — Earnings before Interest, Tax, Depreciation, Amortization
- **CPL** — Cost Per Lead = `Adspend / Total Leads`
- **NBV** — Net Book Value = Cost − Accumulated Depreciation
- **Functional currency** — the currency of the primary economic environment in which Tuitional operates (AED)

## 14. What this system is NOT

For the avoidance of scope creep:

- **Not a tax engine.** UAE VAT (5%) and Pakistan withholding are out of scope for Phase 1–6. The COA contains a `Tax Payable` account but it is not auto-computed.
- **Not a billing system.** Wallet top-ups are recorded; the actual collection mechanism (Stripe, PayTabs, bank transfer) is upstream and feeds in via bank statement reconciliation.
- **Not an LMS.** Sessions are read from the existing LMS; we do not schedule or run them.
- **Not a payroll system for tutor disbursement.** We compute what is owed and produce a payable schedule; the actual payouts are done via bank transfer outside this system.
- **Not the source of truth for HR.** Teacher-absent and tutor quality metrics are tracked in a separate sub-ledger but HR personnel data is not managed here.
