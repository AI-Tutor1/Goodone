# Ingestion Rules

Rules every ingestion adapter must obey. Bugs at this layer poison the ledger silently — discipline here is non-negotiable.

## 1. Universal rules (apply to every adapter)

1. **Idempotency.** Running the same ingest twice produces no duplicates. Adapters track a unique source ID (LMS session ID, bank txn ref, sheet row hash). Duplicates are detected and skipped, not re-inserted.
2. **No silent absorption.** Any row that fails validation goes to `data_quality_quarantine` with a reason code. Never dropped, never auto-corrected.
3. **Atomic batch.** A batch either commits in full or rolls back. No partial commits.
4. **Append-only source records.** Once ingested, source records are immutable. Corrections come as new records (e.g., LMS resends an updated session → it's a new row that supersedes; we keep both for audit).
5. **Timestamped.** Every ingested row records `ingested_at`, `source`, `source_record_id`, `adapter_version`.
6. **Backfill safe.** All adapters accept a date range. Re-ingesting historical data is allowed and idempotent.

## 2. LMS Adapter

**Source:** Tuitional LMS API (interface to be confirmed; mock implementation for Phase 2; real wiring in Phase 3 contingent on API access).

**Records ingested:**
- Sessions (with status, conducted_minutes, scheduled_minutes, enrollment_id)
- Enrollments (student_id, tutor_id, subject, grade, curriculum, dates)
- Tutors (master data, refreshed)
- Students (master data, refreshed)

**Validation rules for sessions:**

| Rule | Pass | Quarantine |
|---|---|---|
| `enrollment_id` exists in `enrollments` | row enters | reason: `unknown_enrollment` |
| `status` in {conducted, student_absent, teacher_absent, cancelled, no_show} | row enters | reason: `unknown_status` |
| `scheduled_minutes` > 0 and ≤ 240 | row enters | reason: `bad_scheduled_minutes` |
| `conducted_minutes` ≥ 0 and ≤ scheduled_minutes + 60 | row enters | reason: `bad_conducted_minutes` |
| If status = conducted, `conducted_minutes` > 0 | row enters | reason: `conducted_with_zero_minutes` |
| Session date is not in the future | row enters | reason: `future_dated` |
| Session date is in an open period | row enters | reason: `closed_period_late_arrival` (CFO must reopen or post adjustment) |
| Tutor has a rate for `(tutor × subject × grade × curriculum)` effective on session date | row enters | reason: `missing_tutor_rate` |
| Student rate exists for `(subject × grade × curriculum)` effective on session date | row enters | reason: `missing_student_rate` |

**Cadence:** hourly poll (or webhook if LMS supports). Late arrivals (LMS sends a session > 24h after it occurred) flagged but accepted.

## 3. Sheets Adapter

**Source:** Google Sheets accessed via service account.

**Sheets ingested:**
- `ad_spend` — date, channel, campaign, amount_aed, leads
- `manual_entries` — month-1 payroll backfill, ad-hoc entries
- `permanent_teacher_hours` — monthly hours per permanent teacher
- `master_overrides` — CFO can patch FX rates, override student/tutor rates exceptionally

**Validation rules:**

- Sheet schema (column names) must match expected; mismatches quarantine the whole batch (not row-by-row).
- Numeric fields must parse; commas accepted as thousands separators.
- Currency fields default to AED unless tagged.
- Each row has a `row_hash` computed for idempotency.

**Cadence:** Daily for `ad_spend`; on-demand for the rest.

## 4. Bank Statement Adapter

**Source:** CSV upload via dashboard. Multi-bank support via column-map config per account.

**Records ingested:** `bank_transactions` — date, amount, debit/credit, description, reference, balance_after.

**Validation rules:**

- Amount must parse as decimal.
- Running balance must be consistent with prior row + this row's amount (if balance column present). Inconsistency → quarantine entire CSV.
- Date must be ISO-parseable.
- Reference must be non-empty (used for matching to system events).

**Matching to system events:**

- Incoming receipts → matched to expected wallet top-ups by amount + date proximity + reference.
- Outgoing payments → matched to tutor payments, vendor payments, or other expected outflows.
- Unmatched → flagged in dashboard for CFO to manually link or post a JE.

**Cadence:** On-demand upload. Reconciliation report runs after upload.

## 5. FX Rate Puller

**Source:** `https://api.exchangerate.host/latest?base=AED&symbols=PKR` (or equivalent).

**Validation:**

- Rate must be > 0 and within ± 5% of last 7 days' average. Outliers flagged but stored (for review).
- If API down for > 24 hours, last known rate carries forward; alert raised.

**Manual override:** CFO can set a rate per date via the dashboard; manual rates take precedence. Source field tagged `manual` and `set_by`.

**Cadence:** Daily 00:30 UTC.

## 6. Manual Upload Adapter (Month-1 Payroll, Screenshots)

**Source:** CFO/operator uploads a CSV/JSON via dashboard, mapped to a one-time backfill job.

**Validation:**

- Operator confirms the period and source description.
- Each row gets a synthetic source_record_id prefixed `MANUAL_<batch_id>_<row>`.
- Operator must sign off on the batch summary before posting.

**Use case:** Month-1 historical payroll where you said you'd provide screenshots. The first month's data goes in via this path; subsequent months via the LMS/sheets adapters.

## 7. Quarantine Workflow

A row in `data_quality_quarantine` has:

```
quarantine_id
adapter_name
source_record_id
raw_payload (json)
reason_code
reason_detail
quarantined_at
resolved (bool)
resolution_action  (one of: reprocess, drop, manual_jes_posted)
resolution_notes
resolved_by
resolved_at
```

CLI commands (Phase 3):
- `tuitional quarantine list` — list open quarantine items
- `tuitional quarantine inspect <id>` — show full payload
- `tuitional quarantine reprocess <id>` — push back through the adapter (after upstream fix)
- `tuitional quarantine drop <id> --reason "..."` — discard with reason

Dashboard view (Phase 5) mirrors the CLI.

**Quarantine SLA:** Items in quarantine > 7 days raise an alert. Period close is hard-blocked if any quarantine item touches the closing period.

## 8. Performance and rate limits

- LMS adapter: respect API rate limits; back off exponentially on 429.
- Sheets API: bulk reads (one round-trip per sheet); cached for 5 minutes.
- FX API: free tier sufficient (1 call/day per pair).
- All adapters log their start, end, rows in/out, errors.

## 9. Versioning

Each adapter stamps its version on every ingested row (`adapter_version`). When an adapter changes behavior in a way that affects historical interpretation (e.g., new validation rule retroactively), the migration tagged with the version must document this. Re-running an adapter on historical data must be considered carefully — generally it should be opt-in, not automatic.
