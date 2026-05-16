---
name: memex:steward:reconcile-orphan
description: Authorized fix-up of a flagged orphan (Index → missing-store-row, or store-row → missing-Index-entry). Requires explicit invocation; never automatic.
---

# memex:steward:reconcile-orphan

## When to use

After reviewing an audit report and deciding how to resolve a specific finding.

## Inputs

- `index_id` — the orphaned row's identifier
- `action` — one of:
  - `delete-index` — remove the documents row and its relations (target row is already gone)
  - `reindex` — re-run Librarian on the target store row (fixes reverse orphan)
  - `note` — leave as-is but mark the finding as acknowledged in the audit log

## Invocation

Implementation deferred to Plan 3 acceptance; v0.2 Plan 2 ships only the SKILL.md describing the contract.
