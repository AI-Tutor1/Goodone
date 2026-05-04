# IFRS Treatments

Tuitional follows IFRS for management reporting. This document captures the specific accounting policies the system implements. These are the policies the agents and the COA encode; they should be reviewed by an external auditor before any external reporting is produced.

## 1. Revenue Recognition (IFRS 15)

**Policy:** Revenue is recognized when the performance obligation is satisfied — i.e., when a tutoring session is conducted (or when a student-absent session occurs and the no-show charge is earned per contract).

**Wallet model treatment:**

- Student top-ups are **contract liabilities** under IFRS 15. They are recorded in `2050 Deferred Revenue — Student Wallets` until consumed.
- The performance obligation is the delivery of a tutoring session.
- Revenue is recognized at the point in time the session is conducted (point-in-time, not over-time, because each session is distinct).
- The transaction price for a session = `student_hourly_rate × scheduled_hours` (or actual session length if billed differently — current rule: scheduled).

**Refunds and returns:**

- Refundable wallet balances do NOT meet the criteria for revenue recognition until consumed. They remain as contract liabilities indefinitely (no expiry per current policy).
- The estimated refund rate (variable consideration) is currently zero in the model — refunds reduce the liability when paid, never reduce historical revenue. This is conservative and consistent with the no-expiry policy.

**Significant financing component:** None considered. The wallet balance is held for short-to-medium term and there is no interest or premium on top-up. If average wallet age exceeds 12 months in aggregate, this assumption should be revisited.

**Aging:**

- Wallet balances dormant > 12 months are flagged for management attention.
- They are NOT written off (no expiry).
- If policy changes to introduce expiry, the breakage methodology under IFRS 15 (B46) is implemented in account `4030 Breakage Revenue`.

## 2. Foreign Exchange (IAS 21)

**Functional currency:** AED. This is the currency of the primary economic environment (UAE entity, AED revenue, AED bank).

**Foreign currency transactions:**

| Item | Translation rule |
|---|---|
| P&L items (revenue, expenses) | Monthly average AED/PKR rate |
| Monetary balance sheet items at month-end (PKR tutor payable, PKR cash) | Closing rate |
| Non-monetary balance sheet items (fixed assets, intangibles, prepaids) | Historical rate at acquisition |
| Equity | Historical rate at issuance |

**Why this matters:** A naive "use one rate for everything" approach creates phantom FX gains/losses that distort P&L. The split treatment isolates real FX impact.

**Realized vs unrealized:**

- **Realized FX gain/loss** (account 7010) — booked when actual cash settles a foreign-currency liability or receivable (i.e., when tutors are paid on the 10th).
- **Unrealized FX gain/loss** (account 7020) — booked at month-end revaluation; reversed first day of next month so the next realized entry isn't double-counted.

**Rate source:**

- Daily rates auto-pulled from `exchangerate.host` (free, ECB-based for AED, supplemented for PKR via central bank reference).
- Stored in `fx_rates` table with `source` field tagged `auto` or `manual`.
- Manual override per-day is supported and takes precedence.
- Month-end closing rate: rate as of the last calendar day of the month.
- Monthly average: arithmetic mean of daily rates for the month (weighted average of business-day-only rates is an option for later).

**Operational notes:**

- The rate convention stored is `aed_to_pkr` (1 AED = X PKR; X ~ 76 typically).
- Conversions: `pkr_amount = aed_amount × rate`, `aed_amount = pkr_amount / rate`.
- The CFO confirms rates monthly; the system flags any single-day move > 5% for review.

## 3. Property, Plant and Equipment (IAS 16)

**Recognition:** An item is capitalized as PPE if cost ≥ AED 1,000 and useful life > 1 year. Below threshold → expensed (`6440 Office Supplies`).

**Cost:** Purchase price + directly attributable costs (delivery, installation). VAT included only if non-recoverable.

**Depreciation:**

| Class | Useful life | Method | Residual value |
|---|---|---|---|
| Laptops | 3 years | Straight-line | 0 |
| Furniture | 5 years | Straight-line | 0 |
| Office equipment | 5 years | Straight-line | 0 |

Monthly depreciation = `cost / (useful_life_years × 12)`. Computed and posted on the first day after period close.

**Disposal:** When an asset is disposed, the gain/loss = `proceeds − NBV` is posted to `7050 Asset Disposal Gain/Loss`. The cost and accumulated depreciation are derecognized.

**Impairment:** Not modeled in Phase 1–6 (immaterial given asset base). To be added if asset base grows.

**Existing assets at system go-live:**

- 15 laptops × AED 1,000 cost, ~3 years old → fully depreciated (NBV = 0). Loaded with cost = 1000, accumulated depreciation = 1000 each.
- Furniture: 20 chairs × AED 500 + 5 tables × AED 1,500 = AED 17,500 cost; assume ~3 years old → 60% depreciated. Loaded with NBV ≈ AED 7,000 in aggregate.

**Override:** If actual purchase records exist, they take precedence and are loaded directly.

## 4. Intangible Assets (IAS 38) — particularly Tuitional AI

**Internally generated software development costs** are split into:

- **Research phase** — expensed as incurred. Includes initial concept, feasibility studies before the product was definitively decided to be built.
- **Development phase** — capitalized only if ALL six criteria of IAS 38.57 are met:
  1. Technical feasibility of completing the asset is demonstrated
  2. Intent to complete and use/sell the asset
  3. Ability to use or sell the asset
  4. Probable future economic benefits
  5. Adequate technical, financial, and other resources to complete
  6. Ability to measure attributable expenditure reliably

**Tuitional AI specifically:**

- **Feasibility established:** May 2024 (24 months prior to system go-live).
- **Capitalization start:** May 2024.
- **Capitalizable cost:** Allocated portion of developer salary + directly attributable cloud infra (if separable). Currently 1 dev × AED 4,000/month × 50% = AED 2,000/month.
- **Cumulative capitalized as of Phase 1 go-live (May 2026):** 24 × AED 2,000 = AED 48,000 → loaded as opening balance in `1121`.
- **Launch date:** ~June 2026 (operator estimate). On launch, balance reclassifies from `1121` to `1122`.
- **Useful life post-launch:** 5 years, straight-line.
- **Monthly amortization post-launch:** ~AED 800/month at current accumulation; recalculated at launch based on actual carrying amount.

**Important caveat:** The capitalization decision is judgmental. An external auditor should review the IAS 38.57 criteria documentation (intent, feasibility, economic benefit) before any external reporting. The system records what management believes the policy is; it does not validate the underlying judgment.

**Subsequent costs:** Post-launch development costs that enhance functionality are capitalized; maintenance and bug fixes are expensed. Distinguishing the two is operator-driven (developer time-tracking with capex/opex tagging).

## 5. Prepaid Expenses

**LMS license** (AED 15,000/year): paid annually upfront. Recorded as prepaid in `1051`, amortized straight-line over 12 months at AED 1,250/month to `6310 LMS License Amortization`.

**Other prepaids:** Same treatment. Tracked in sub-ledger `prepaid` with schedule per item.

## 6. Provisions and Contingent Liabilities (IAS 37)

Not currently modeled. If material provisions arise (legal disputes, restructuring, onerous contracts), they will be added to the COA in 2090s range and posted manually by CFO with documentation.

## 7. Employee Benefits (IAS 19)

Tutors are independent contractors → not in scope of IAS 19.

For salaried staff:

- Salaries: expensed monthly when earned (accrued at month-end if paid in arrears).
- End-of-service gratuity (UAE Labour Law): accrued monthly per UAE statutory formula. Currently captured in `6170 Employee Benefits` as a flat operator estimate; should be replaced with a per-employee accrual schedule when staff count grows.
- Annual leave: not currently accrued (immaterial). Add when staff count > 20.

## 8. Income Tax (IAS 12)

UAE Corporate Tax (effective June 2023, 9% on taxable income above AED 375,000) is **not currently modeled**. The COA has `2070 Tax Payable` as a placeholder. To be implemented:

- Once monthly profitability is established, a tax expense estimate per IAS 12 is computed.
- Deferred tax on temporary differences (e.g., depreciation timing differences, capitalized dev costs) becomes relevant once external reporting begins.
- This is explicitly out of scope for Phase 1–6. An accountant should be engaged before first external reporting.

## 9. Statement of Cash Flows (IAS 7)

Indirect method. Generated by the Reporting Agent from changes in BS items and P&L. Categories:

- Operating activities: net profit + non-cash adjustments + working capital changes
- Investing activities: PPE purchases/disposals, intangible additions
- Financing activities: equity raises, debt (none currently)

## 10. Materiality

The system records every transaction; there is no de minimis threshold within the books. Materiality applies to:

- **Reporting presentation** — small accounts may be aggregated in external reports
- **Audit attention** — but that is external

For internal management reporting, all postable accounts appear individually if they have any activity in the period.

## 11. Document version

| Version | Date | Change | Approver |
|---|---|---|---|
| 1.0 | 2026-05-04 | Initial Phase 1 draft | (pending CFO) |
