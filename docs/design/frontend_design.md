# Frontend Design — CFO Dashboard

The frontend is a React SPA built with Vite and styled with Tailwind. It serves a single power user (the CFO) initially, with role-based access scaffolded for later expansion (department heads, FA, tutors).

## 1. Stack

- **React 18** + TypeScript (strict)
- **Vite** for build/dev
- **Tailwind CSS** for styling, with a small custom theme (no DaisyUI / shadcn for MVP — keep dependencies minimal)
- **TanStack Query** (React Query) for server state
- **TanStack Table** for data grids (the CFO will spend most time in tables)
- **Recharts** for charts (lightweight, sufficient)
- **React Router** for navigation
- **React Hook Form** + Zod for forms and validation
- **openapi-typescript** to generate API types from FastAPI's OpenAPI spec
- **Day.js** for dates (timezone-aware, lightweight vs. moment)

No state management library beyond Query — keeps it simple.

## 2. Layout

Three-zone layout:

```
┌─────────────────────────────────────────────────────────────┐
│  Header: logo · current period · quick search · user menu   │
├──────────┬──────────────────────────────────────────────────┤
│  Side    │                                                   │
│  Nav     │             Main content area                     │
│          │                                                   │
│  - Home  │                                                   │
│  - Reports│                                                   │
│  - Ledger│                                                   │
│  - Subs  │                                                   │
│  - Sanc  │                                                   │
│  - Period│                                                   │
│  - Master│                                                   │
│  - Chat  │                                                   │
│          │                                                   │
└──────────┴──────────────────────────────────────────────────┘
```

Sidebar collapsible. Header sticky. Content scrollable.

## 3. Pages

### 3.1 Home
- KPI cards (current MTD): Revenue, Gross Margin, EBITDA, Cash, Wallet Liability, Tutor Payable
- Charts: 12-month revenue trend, EBITDA trend
- Alerts panel: open quarantine, pending FA/CFO approvals, period close status, FX rate not confirmed
- "Things needing attention" list

### 3.2 Reports
Tabs: P&L | Balance Sheet | Cash Flow | KPIs | Profitability

- Period selector (month / quarter / year-to-date / custom)
- Comparison toggle (vs. prior period, vs. prior year, vs. budget [later])
- Drill-down: click any line → see the underlying journal entries
- Export: PDF, XLSX, CSV (all server-rendered)

### 3.3 Ledger
- Journal Entry list with filters (date range, account, dimension, source, posted_by)
- JE detail view: lines, attachment, source ref, audit trail
- "New JE" button → manual journal entry form
- Reverse JE action (CFO only, with confirmation)

### 3.4 Sub-ledgers
Tabs: Student Wallets | Tutor Payable | Fixed Assets | Prepaids | Intangibles | Sanction Memos

- Each tab: searchable, filterable table; row → detail
- Wallet aging view (0-30, 31-90, 91-180, 181-365, > 365 days)
- Tutor payable: per-tutor balance + currency + last accrual + last payment
- Fixed asset: cost, accumulated dep, NBV, useful life, period-by-period dep schedule
- Prepaid/intangible: total, schedule, monthly amort, unamortized balance

### 3.5 Sanctions
- Queue view (pending FA, pending CFO, all)
- Filters: status, department, amount range, date submitted
- Per-request detail: history, attachments, comments, approve/reject buttons (with required comment)
- Linked spend column (which JEs hit this sanction)

### 3.6 Period
- All periods listed with status (OPEN, IN_CLOSING, CLOSED, REOPENED)
- Current period: close-readiness checks panel (red/green per check)
- Close period button (when ready)
- Reopen button (CFO, with reason)
- Per-period: links to all generated reports

### 3.7 Master data
Tabs: Tutors | Students | Enrollments | Tutor Rates | Student Rates | FX Rates

- Tutor Rate management is the most-used: edit `(tutor × subject × grade × curriculum) → rate` with effective dating
- Bulk upload via CSV
- Audit log per change

### 3.8 Chat (CFO only)
- Conversational interface to the LLM-backed CFO chat agent
- Side panel showing what tools the agent invoked (transparency)
- Conversation history saved
- "Ask a question" examples for new users

## 4. Forms

### Manual JE form

- Date picker (constrained to open periods)
- Narration (required, ≥ 10 chars)
- Lines repeater: account picker (autocomplete from COA), Dr/Cr toggle, amount input
- Running total: live balance check (✓ when Dr = Cr)
- Dimensions per line (enrollment_id, department, etc., as relevant)
- Attachment upload (with size/mime check)
- Submit disabled until Dr = Cr and all required fields filled
- Confirmation dialog: shows the final JE for review before posting

### Sanction request form (department heads)

- Minimal, mobile-friendly (department heads may submit from phone)
- Token-auth via emailed link
- Fields per `approval_rules.md` §2
- Save as draft, submit when ready

## 5. Tables (CFO will live here)

Common features:
- Server-side sort / filter / pagination
- Sticky header on scroll
- Column resize, column hide, column reorder (preferences saved per-user)
- Inline number formatting: `1,234,567.89` with currency suffix
- Negative numbers: red (color-blind safe — also leading minus)
- Click row → detail panel slides in from right (drawer pattern)
- "Export visible" button for current filtered view

## 6. Charts

- Line: revenue/EBITDA trend (12 months)
- Bar: revenue by enrollment top 20
- Stacked bar: cost composition (tutor cost, salaries, marketing, etc.)
- Sparklines on KPI cards

Theme: monochrome with one accent color. Easy to read, print-friendly.

## 7. Number display rules

- All AED amounts: `AED 1,234.56` (currency code prefix + comma thousands + 2 dp)
- All PKR amounts: `PKR 1,234,567.00` (typically larger numbers)
- Negative: `(AED 1,234.56)` parentheses-style, also red text
- Percentages: 1 dp (e.g., `42.5%`)
- Ratios (LTV/CAC): 2 dp (e.g., `3.42x`)

## 8. Loading and error states

- Skeleton loaders for tables and cards (no spinners)
- Empty states: helpful copy, no decorative illustrations
- Error states: clear what went wrong, what to do, link to support
- Stale data indicator if Query refetch is in flight

## 9. Keyboard shortcuts (power user)

- `g h` — go home
- `g r` — go reports
- `g l` — go ledger
- `n j` — new journal entry
- `/` — focus quick search
- `?` — show shortcut help

## 10. Accessibility

- Lighthouse a11y score ≥ 90
- All interactive elements keyboard-navigable
- ARIA labels on all icon-only buttons
- Color contrast WCAG AA minimum (AAA where reasonable)
- Focus trap in modals
- Screen reader text where icons replace labels

## 11. Authentication UI

- Login: email + password, optional TOTP
- Session expiry: 8 hours of inactivity; warn at 7:30
- Logout button always accessible from user menu
- TOTP enrollment guided flow

## 12. What is NOT in the frontend (Phase 5)

- Tutor self-service portal
- Department head dashboard (only the request form)
- Student-facing UI
- Mobile-optimized layouts (tablet+ only in Phase 5)
- Advanced visualizations beyond the listed charts
- Real-time updates / websockets (TanStack Query polling is enough)
