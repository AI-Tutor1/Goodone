# API Design

The FastAPI backend exposes REST endpoints consumed by the React frontend. Internal-only: not exposed to public internet (except the click-through approval URL with one-time tokens). All endpoints require auth (session cookie) unless explicitly marked public.

## 1. Conventions

- Base path: `/api/v1`
- JSON request/response only (multipart for uploads)
- All money amounts: string-encoded Decimal with 2 dp (avoid float). Frontend parses to Decimal.js or similar.
- Dates: ISO 8601 (`YYYY-MM-DD`), times: ISO 8601 with timezone.
- Pagination: cursor-based; `limit` (default 50, max 200), `cursor` (opaque).
- Errors: RFC 7807 problem details JSON.
- Idempotency: mutating endpoints accept `Idempotency-Key` header.

## 2. Auth

```
POST   /api/v1/auth/login            email + password (+ TOTP if enabled)
POST   /api/v1/auth/logout
GET    /api/v1/auth/me
POST   /api/v1/auth/totp/enroll
POST   /api/v1/auth/totp/verify
```

Session cookie: HttpOnly, Secure (in prod), SameSite=Lax. CSRF protection via double-submit token on mutating routes.

## 3. Reports

```
GET    /api/v1/reports/pnl?period=YYYY-MM&format=json|xlsx|pdf
GET    /api/v1/reports/balance-sheet?period_end=YYYY-MM-DD&format=...
GET    /api/v1/reports/cash-flow?period=YYYY-MM&format=...
GET    /api/v1/reports/kpis?period=YYYY-MM
GET    /api/v1/reports/profitability?period=YYYY-MM&filters=...
GET    /api/v1/reports/tutor-payable?period=YYYY-MM&format=...
GET    /api/v1/reports/auditor-pack?year=YYYY                  # year-end zip
```

KPI response includes: revenue, gross margin, EBITDA, EBITDA margin, net profit, ROI, CPL, LTV (rolling 12mo), CAC, LTV/CAC ratio.

## 4. Ledger

```
GET    /api/v1/ledger/journal-entries?period=YYYY-MM&account=...&dimension=...
GET    /api/v1/ledger/journal-entries/{je_id}
POST   /api/v1/ledger/journal-entries                  # CFO manual JE
POST   /api/v1/ledger/journal-entries/{je_id}/reverse  # CFO reversal
GET    /api/v1/ledger/accounts                          # COA listing
GET    /api/v1/ledger/account/{code}/balance?as_of=YYYY-MM-DD
GET    /api/v1/ledger/account/{code}/activity?period=YYYY-MM
```

Manual JE POST body:
```json
{
  "date": "2026-04-15",
  "narration": "Q1 audit fee accrual",
  "lines": [
    {"account_code": "6450", "debit": "5000.00", "credit": "0", "dimension": {"department": "FINANCE"}},
    {"account_code": "2040", "debit": "0", "credit": "5000.00"}
  ],
  "attachment_url": "uploads/2026-04/audit_invoice.pdf"
}
```

Validation per `journal_rules.md`. Returns the posted JE with assigned `je_id`.

## 5. Sub-ledgers

```
GET    /api/v1/subledgers/wallets/students?status=active&aging=true
GET    /api/v1/subledgers/wallets/students/{student_id}
GET    /api/v1/subledgers/wallets/students/{student_id}/transactions?period=...
POST   /api/v1/subledgers/wallets/students/{student_id}/refund     # CFO action

GET    /api/v1/subledgers/tutor-payable
GET    /api/v1/subledgers/tutor-payable/{tutor_id}
POST   /api/v1/subledgers/tutor-payable/payment-run                # generate monthly schedule

GET    /api/v1/subledgers/fixed-assets
POST   /api/v1/subledgers/fixed-assets                             # add new asset
PATCH  /api/v1/subledgers/fixed-assets/{asset_id}                  # update (limited fields)
POST   /api/v1/subledgers/fixed-assets/{asset_id}/dispose

GET    /api/v1/subledgers/prepaids
POST   /api/v1/subledgers/prepaids
GET    /api/v1/subledgers/intangibles
POST   /api/v1/subledgers/intangibles/{id}/launch                  # reclassify 1121 → 1122
```

## 6. Sanctions

```
POST   /api/v1/sanctions                              # dept head submits
GET    /api/v1/sanctions?status=...&department=...
GET    /api/v1/sanctions/{request_id}
POST   /api/v1/sanctions/{request_id}/fa-decide       # FA approve/reject
POST   /api/v1/sanctions/{request_id}/cfo-decide      # CFO approve/reject
POST   /api/v1/sanctions/{request_id}/cancel          # CFO cancel
POST   /api/v1/sanctions/{request_id}/link-spend      # link a JE to this sanction

# Public click-through (token-auth, NOT session)
GET    /api/v1/sanctions/approve/{token}              # render approval page
POST   /api/v1/sanctions/approve/{token}              # submit decision
```

## 7. Periods

```
GET    /api/v1/periods                                # all periods + status
GET    /api/v1/periods/{period}                       # single period detail
POST   /api/v1/periods/{period}/start-close           # start IN_CLOSING
POST   /api/v1/periods/{period}/close                 # finalize
POST   /api/v1/periods/{period}/reopen                # CFO reopen with reason
GET    /api/v1/periods/{period}/close-checks          # status of all hard blocks
```

## 8. Ingestion

```
POST   /api/v1/ingest/lms/run?from=...&to=...         # trigger LMS pull
POST   /api/v1/ingest/sheets/run?sheet=...
POST   /api/v1/ingest/bank/upload                      # multipart CSV upload
POST   /api/v1/ingest/manual-payroll/upload            # month-1 payroll backfill
GET    /api/v1/ingest/runs?adapter=...                 # run history
GET    /api/v1/quarantine?status=open
POST   /api/v1/quarantine/{id}/reprocess
POST   /api/v1/quarantine/{id}/drop
```

## 9. Master data

```
GET    /api/v1/master/tutors
GET    /api/v1/master/students
GET    /api/v1/master/enrollments
GET    /api/v1/master/tutor-rates
POST   /api/v1/master/tutor-rates                      # upsert
GET    /api/v1/master/student-rates
POST   /api/v1/master/student-rates
GET    /api/v1/master/fx-rates?from=...&to=...
POST   /api/v1/master/fx-rates                         # manual override
```

Tutor and student rates use effective-dating; new rates have `effective_from` and an optional `effective_to`. Existing journal entries reference the rate that was effective on the session date.

## 10. Chat (LLM-backed)

```
POST   /api/v1/chat/cfo                                # one turn; conversation_id + message
GET    /api/v1/chat/cfo/conversations
GET    /api/v1/chat/cfo/conversations/{id}
```

The CFO chat agent has read-only access to the ledger and reports. It cannot post journals. Tools available to it: read account balance, read JE details, read sub-ledger views, read reports, read master data. It calls the Anthropic API with these tools.

## 11. Health & ops

```
GET    /api/v1/health                                  # public, returns 200 if alive
GET    /api/v1/health/deep                             # auth required; checks DB, agents, etc.
GET    /api/v1/metrics                                 # Prometheus scrape (auth via header)
```

## 12. Rate limits

- Auth endpoints: 10 req/min per IP
- Approval click-through: 30 req/min per token (handles legitimate retries; tokens single-use otherwise)
- Other authenticated endpoints: 600 req/min per session (generous; unlikely to hit)
- Bulk export endpoints: 5 concurrent per user

## 13. Versioning

`/api/v1` for the foreseeable future. Breaking changes only happen via `/api/v2`. Backwards-compatible additions go in v1.

## 14. OpenAPI

FastAPI auto-generates OpenAPI 3.x at `/api/v1/openapi.json`. Frontend uses this for type generation (`openapi-typescript`).

## 15. What is NOT in the API

- No public read access to financial data
- No third-party integrations
- No write access for non-CFO users beyond the sanction request flow
- No bulk edit
- No deletion endpoints (immutability is by design)
