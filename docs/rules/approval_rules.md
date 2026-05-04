# Approval Rules — Sanction Workflow

The sanction workflow is the only way departments commit company funds. Discipline here protects against runaway spend and creates the audit trail needed for fundraising and audit.

## 1. State machine

```
DRAFT  ──submit──>  PENDING_FA  ──FA approve──>  PENDING_CFO  ──CFO approve──>  APPROVED  ──spend──>  CLOSED
                       │                              │                            │                    
                       │                              │                            │                    
                  FA reject                      CFO reject                  cancel by CFO              
                       │                              │                            │                    
                       └──────────────> REJECTED <────┘                            │                    
                                                                                   │                    
                                                                              CANCELLED
```

States defined:

| State | Meaning |
|---|---|
| DRAFT | Department head started a request, hasn't submitted |
| PENDING_FA | Awaiting Financial Analyst review |
| PENDING_CFO | FA approved; awaiting CFO final approval |
| APPROVED | Both approvals received; budget committed; awaiting spend |
| REJECTED | Either FA or CFO rejected (terminal) |
| CANCELLED | CFO cancels an approved-but-unspent request (terminal) |
| CLOSED | All sanctioned funds spent (terminal); or partial spend with explicit close |

## 2. Required fields on submission

A request transitions DRAFT → PENDING_FA only when the requester provides:

- Department (from a fixed list)
- Requester name (auto from session, but confirmable)
- Amount in AED (Decimal, > 0)
- Purpose (free text, ≥ 50 chars)
- Vendor / counterparty (if known)
- Expected spend month (YYYY-MM)
- Supporting attachment (optional but recommended; required if amount > AED 25,000)
- Account code suggestion (optional; CFO can change at approval)

## 3. Approver assignment

- **Financial Analyst (FA)** — fixed user role; one or many users with the role. First FA to claim handles it. Reassignable.
- **CFO** — fixed user role; typically one person. Cannot delegate. CFO can override FA decisions implicitly by their own decision.

In the current setup (CFO-only consumer), the CFO can be assigned both roles. A request still goes through both approval steps to maintain audit discipline; if the same user is in both roles, both clicks are still required and timestamped separately.

## 4. Notification flow

On state transition:

| Transition | Email to | Subject prefix |
|---|---|---|
| Submit (→ PENDING_FA) | All FA-role users | `[Sanction Request] FA Review Needed` |
| FA approve (→ PENDING_CFO) | CFO | `[Sanction Request] CFO Approval Needed` |
| FA reject | Requester | `[Sanction Request] Rejected by FA` |
| CFO approve (→ APPROVED) | Requester + dept head + FA | `[Sanction Request] APPROVED` |
| CFO reject | Requester + FA | `[Sanction Request] Rejected by CFO` |
| Cancelled | Requester | `[Sanction Request] Cancelled` |
| Spent (→ CLOSED) | Requester | `[Sanction Request] Closed` |

Each email contains a one-time-token URL for the recipient to view (and act on, if applicable). Tokens expire in 7 days; expired tokens redirect to login.

## 5. Click-through approval

The approval link goes to a minimal page showing:

- Full request details
- Attachments
- Prior comments
- Approve / Reject buttons with required comment text
- Reject requires a reason ≥ 20 chars

On click:

- Decision recorded in `sanction_requests` (decision, decision_at, decided_by, decision_note, ip)
- If approved at FA stage: state → PENDING_CFO; CFO email triggered
- If approved at CFO stage: memo journal posted automatically (per `accounting_rules.md` §13)
- If rejected: state → REJECTED; requester notified

## 6. Memo journal lifecycle

When CFO approves:
- A self-balancing memo JE posts to account `2060`, dimensioned by `sanction_request_id` and a `committed/contra` sub-key.
- The sanction sub-ledger reflects the open commitment.

When actual spend occurs (linked to the sanction):
- The memo is reversed in proportion to the spend.
- The actual expense JE posts (Dr expense, Cr cash/AP).

If actual > sanctioned: hard reject the spend post; CFO must approve a new sanction or amend the existing one (amendment = new approval cycle on the delta).

If actual < sanctioned and request is closed: residual memo is reversed; no expense.

## 7. Amendments

A submitted-but-not-approved request can be edited by the requester (returns to DRAFT briefly).

An APPROVED request can be amended by:
- Requester proposing an amendment with reason
- New FA + CFO approval cycle on the delta
- The original approval remains in audit trail

## 8. Cancellation

CFO can cancel any APPROVED request that has not been (fully) spent. Reason required. Memo reversed.

## 9. Audit trail

Every state transition is logged with: timestamp, actor, action, before_state, after_state, comment, IP. Retained indefinitely.

## 10. Phase 5 UI requirements

- Departmental request form (link-shareable; minimal auth — token + dept code)
- FA queue: open requests assigned to me / unassigned
- CFO queue: PENDING_CFO requests
- All-requests browse with filters (status, dept, date, amount range)
- Per-request detail with full history and click-through approve/reject
- Linkage to actual spend records (via JE references)

## 11. Edge cases

- **Late spend after period close.** If spend posts in a later period than the original request, that's fine; memo reversal posts in the spend's period. No backdating required.
- **FA approves, then CFO is unavailable for weeks.** Memo not yet posted. Request sits in PENDING_CFO. No timeout in current rules.
- **Same vendor, multiple requests.** Allowed; each is its own request and memo. CFO sees aggregate by vendor in dashboard if needed.
- **Recurring spend.** Each period's request is separate. (Future: support recurring sanctions with monthly auto-renewal up to a cap.)
