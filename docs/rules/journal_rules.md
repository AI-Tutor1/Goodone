# Journal Posting Rules

These are the engine-level invariants. Every journal entry that touches the GL must satisfy all of them. Violations are hard errors — the engine refuses to post. This is the ledger's most important contract.

## 1. Balance invariant

For every `journal_entry`:
```
SUM(journal_lines.debit_aed)  ==  SUM(journal_lines.credit_aed)
```

Tolerance: zero. Floating-point drift is not acceptable; we use `Decimal` throughout. Database constraint enforces this with a check on insert.

## 2. Account validity

Every `journal_lines.account_code` must:
1. Exist in `chart_of_accounts`
2. Have `is_postable = true`
3. Be `active = true`

Otherwise: rejected.

## 3. Period status

`journal_entries.date` must fall within an **open** period at the moment of posting.

- Periods are defined as calendar months (`YYYY-MM`).
- A period transitions to `closed` via the period close workflow.
- Any insert/update with `date` in a closed period is rejected.
- The CFO can reopen a period (logged); only then can entries be posted.

## 4. Sub-ledger consistency

If a journal line targets an account marked with a `sub_ledger`, the line MUST include the sub-ledger key:

| account.sub_ledger | required key on line |
|---|---|
| student_wallet | student_id |
| tutor_payable | tutor_id |
| fixed_asset | asset_id |
| prepaid | prepaid_id |
| intangible | intangible_id |
| sanction_memo | sanction_request_id |

Sub-ledger keys are stored in `journal_lines.sub_ledger_keys` (JSONB column).

If the key is missing or doesn't exist in the sub-ledger registry → rejected.

## 5. Dimensions

Optional but recorded when applicable:

| Dimension | When required |
|---|---|
| `enrollment_id` | Revenue (4xxx) and direct cost (5xxx) lines from a session |
| `department` | Operating expense (6xxx) lines tied to a department |
| `tutor_id` | Tutor-related lines (already in sub-ledger when applicable) |
| `campaign_id` | Marketing spend lines, when known |
| `cost_center` | Future use |

Dimensions enable per-enrollment, per-department, per-campaign reporting without requiring separate accounts.

## 6. Source attribution

Every journal entry records:

- `source` — one of: `system:agent_name`, `manual:user_id`, `import:adapter_name`
- `source_ref` — pointer back to the originating record (session_id, sanction_request_id, etc.)
- `adapter_or_agent_version` — for reproducibility

This makes every line in the GL traceable to its origin.

## 7. Immutability

Posted journal entries cannot be:
- Edited (any field)
- Deleted

Corrections are made by **reversal** + **new entry**, where the reversal references the original via `reverses_je_id`.

A reversal entry's lines are the negatives of the original. The engine has a helper `reverse_journal(je_id, narration)` for this.

## 8. Sequence and dating

- `je_id` is system-generated, monotonic.
- `date` is the **economic date** — when the underlying event happened. Can be backdated within an open period.
- `posted_at` is wall-clock time of posting; always now().
- A JE's date can differ from its posted_at (e.g., a session conducted yesterday but ingested and posted today).

## 9. Currency

- All `debit_aed` / `credit_aed` are in AED. Period.
- For sub-ledgers that track an original currency (e.g., PKR tutor payable), the original-currency amount and rate used are stored on the **sub-ledger entry**, not on the journal line.
- Single-currency GL → simpler reporting, no consolidation arithmetic.

## 10. Mandatory fields by source

### System-posted (from agents)
- `narration` (auto-generated; format: `<agent>: <event_type> <reference>`)
- All standard fields

### Manual (CFO)
- `narration` (free text, ≥ 10 chars)
- `attachment_url` (required if total > AED 50,000; recommended otherwise)
- `posted_by` (auto)
- `posted_at` (auto)

### Import (e.g., backfill)
- `narration` (auto: `IMPORT <batch_id> <row_id>`)
- `import_batch_id`
- Operator sign-off recorded before posting

## 11. Anomaly checks (soft warnings, do not block)

The engine emits a warning (logged + surfaced in dashboard) when:

- Two manual JEs with same date, same accounts, same amount within 1 hour (potential duplicate)
- A JE > AED 50,000 without attachment
- A JE that would push a sub-ledger balance negative (e.g., wallet to negative) — this is HARD blocked, not soft

## 12. Reconciliation guarantees

Daily background job verifies, for each control account with a sub-ledger:
```
gl_balance(account)  ==  SUM(sub_ledger_balances for that account)
```

Any mismatch:
1. Logged as critical
2. Period close is blocked until resolved
3. CFO is alerted

This catches engine bugs that violate sub-ledger consistency despite the upfront validation.

## 13. Performance

Posting one journal entry is a small atomic transaction. With Postgres + appropriate indexes, latency should be < 50ms for an entry with up to 10 lines. Bulk imports use a separate batch path that posts many JEs in one transaction; this path still validates each invariant per JE.

## 14. Audit log

Beyond the `journal_entries` and `journal_lines` tables, every posting action also writes to `audit_log`:

```
audit_log: (timestamp, actor, action, target_type, target_id, before_state, after_state, ip)
```

This captures *attempts* including rejected ones, while the journal tables only capture *successes*.
