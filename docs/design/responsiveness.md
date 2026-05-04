# Responsiveness Design

The CFO will primarily use this on desktop. Tablet (iPad) is supported. Mobile is supported only for two specific flows: the sanction request form (department heads, mobile-first) and the email-triggered approval click-through page.

## 1. Breakpoints (Tailwind defaults)

| Name | Min width | Primary use |
|---|---|---|
| `sm` | 640px | Approval click-through; sanction form |
| `md` | 768px | Tablet; basic dashboard read-only |
| `lg` | 1024px | Standard desktop layout |
| `xl` | 1280px | Wide desktop; default target |
| `2xl` | 1536px | Ultra-wide; tables expand to use space |

Default design target: `xl` (1280px). Anything smaller progressively simplifies.

## 2. Per-page responsiveness

### Home dashboard
- `xl+`: 4 KPI cards across, charts side-by-side
- `lg`: 2 KPI cards across, charts stacked
- `md`: 2 KPI cards across, charts stacked, alerts below
- `sm`: single column; not the primary use case but readable

### Reports
- `xl+`: full-width tables with all columns visible
- `lg`: same with horizontal scroll on wide tables
- `md`: column hide menu surfaces; user picks which columns to show
- `sm`: cards-instead-of-rows fallback (read-only, slow but functional)

### Ledger / Sub-ledger tables
- Always have horizontal scroll on smaller viewports
- Sticky first column (account / entity name) so scroll still makes sense
- Detail drawer takes full screen on `md` and below

### Manual JE form
- `xl+`: form on left, live preview on right
- `lg`: form full width, preview below
- `md`: same; line repeater becomes vertical
- `sm`: not supported. Form requires desktop. Show "Please use a desktop browser to post journal entries" message if user lands here on mobile.

### Sanctions
- Queue view: `lg+` table; `md` cards; `sm` cards
- Detail view: `md+` two-column (request details + history); `sm` stacked

### Sanction request form (department heads)
- Mobile-first design. Works perfectly on `sm`.
- Single-column form, large tap targets.
- Attachment upload tested on iOS Safari and Android Chrome.
- Auto-save draft every 30s (avoid lost work on flaky connections).

### Approval click-through page
- Mobile-first. The FA/CFO will often approve from phone.
- Single page, large Approve / Reject buttons.
- Required comment textarea above the buttons (cannot tap until populated).
- One-time-token URL; works without login.

### Period close page
- `lg+`: full layout with checks panel
- `md`: stacked
- `sm`: read-only summary; close action requires desktop (intentional — period close is a high-stakes action that should not happen from a phone)

## 3. Specific patterns

### Tables on small screens

When a table is too wide for the viewport, prefer (in order):

1. Horizontal scroll with sticky first column (default for `lg` and below)
2. Column hide controls (user picks 3-5 visible columns from a menu)
3. Card layout (each row becomes a small card; heavyweight, used as a last resort on `sm`)

Never auto-truncate to the point that information is lost. If we have to hide, we hide visibly.

### Charts on small screens

- Reduce data density (e.g., 12 months → 6 months on `md`)
- Increase font size (don't shrink labels)
- Tooltip-on-tap rather than hover

### Modals vs. drawers vs. full-screen

- `xl+`: modals for short interactions (≤ 5 fields), drawers for longer (JE detail)
- `lg`: same
- `md`: drawer becomes full-width (still slides from right)
- `sm`: every modal/drawer becomes a full-screen page

### Forms

- Always full-width inputs on `sm`
- Labels above inputs (never beside, except checkboxes)
- Currency inputs always have currency code visible
- Date pickers: native HTML5 input on `sm` (better mobile UX), custom on desktop

## 4. What works and what doesn't on each viewport

| Viewport | Read | Drill into reports | Submit JE | Approve sanction | Close period |
|---|---|---|---|---|---|
| Desktop `xl+` | ✅ | ✅ | ✅ | ✅ | ✅ |
| Laptop `lg` | ✅ | ✅ | ✅ | ✅ | ✅ |
| Tablet `md` | ✅ | ✅ (scroll) | ✅ (cramped) | ✅ | ⚠️ Read-only |
| Phone `sm` | ✅ (cards) | ⚠️ Limited | ❌ Blocked | ✅ | ❌ Blocked |

The blocks on phone are intentional. Posting a JE or closing a period demands desktop precision.

## 5. Performance budgets

- Initial JS bundle: ≤ 200 KB gzipped (no MUI, no AntD; Tailwind + light components keep this achievable)
- TTI (time-to-interactive) on 3G: ≤ 3s for the home page
- Lighthouse Performance score: ≥ 85 on desktop, ≥ 70 on mobile

## 6. Browser support

- Chrome, Firefox, Safari, Edge — last 2 major versions
- iOS Safari 16+
- Android Chrome 110+
- IE: unsupported

## 7. Print

- Reports are printable; CFO may want a hard copy for board meetings
- `@media print` styles hide nav, expand content, force black-on-white
- Paginated table headers repeat
- Page numbers in footer

## 8. Dark mode

Out of scope for Phase 5. Add later if requested.

## 9. Localization

English only in Phase 5. Arabic RTL support designed for but not implemented (Tailwind has good RTL story; can be enabled per-route later).
