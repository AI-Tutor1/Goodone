# Conductor Context

This file is consumed by the wshobson/agents `conductor` plugin when invoked from Claude Code. It tells the conductor where to find authoritative project context.

## Project root context
- /CLAUDE.md
- /README.md

## Domain context (must read before any non-trivial task)
- /docs/context.md
- /docs/architecture.md
- /docs/plan.md

## Specification (the rules code must conform to)
- /docs/chart_of_accounts.yaml
- /docs/chart_of_accounts.md
- /docs/accounting_rules.md
- /docs/ifrs_treatments.md
- /docs/rules/journal_rules.md
- /docs/rules/ingestion_rules.md
- /docs/rules/approval_rules.md
- /docs/rules/period_close_rules.md

## Design (for backend / frontend tasks)
- /docs/design/api_design.md
- /docs/design/frontend_design.md
- /docs/design/responsiveness.md

## Quality
- /docs/qa/test_plan.md
- /docs/qa/smoketests.md

## Operational runbooks
- /docs/runbooks/month_end_close.md
- /docs/runbooks/period_reopen.md
- /docs/runbooks/fx_rate_override.md
- /docs/runbooks/disaster_recovery.md

## Workflow

For any task touching the calculation core, ledger engine, or sub-ledgers:
1. Context gather — read all files above marked Domain + Specification
2. Spec — write what the change does, what tests would prove it correct
3. Plan — list the files to touch, in order
4. Implement — make changes in order, run tests after each

For frontend or API work, the Design docs are added to the context gather step.
