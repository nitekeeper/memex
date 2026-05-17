---
name: memex:steward:reconcile-orphan
description: Authorized fix-up of a flagged orphan. Four actions — delete-index (remove documents row), repair (backfill row_id when target exists), reindex (re-run Librarian; deferred), note (acknowledge). Raises OrphanNotFoundError when index_id is unknown or, for repair, already linked.
---

# memex:steward:reconcile-orphan

## When to use

After reviewing an audit report and deciding how to resolve a specific finding,
**or** after a consumer's bootstrap sweep detects orphan-class rows in its own
store and needs to either delete the dangling Index row or backfill the link.

## Inputs

- `index_id` — the orphaned row's identifier
- `action` — one of:
  - `delete-index` — remove the `documents` row and its `relations` rows (use when the target store row is gone, or when no matching target row can be found by other means)
  - `repair` — backfill `documents.row_id` from a known target PK (use when the target row exists but the link was never written — the forward-orphan class where Index committed, target committed, but the `row_id` write was lost). Requires `repair_row_id`.
  - `reindex` — re-run Librarian on the target row (reverse-orphan case; deferred — raises `NotImplementedError`)
  - `note` — leave as-is but record acknowledgment in `~/.memex/audits/reconciliation-log.md`
- `repair_row_id` *(repair only)* — the target store's primary-key value to bind into `documents.row_id`
- `note_text` *(note only)* — free-form acknowledgment text

## Errors

- `OrphanNotFoundError(index_id)` — raised when `index_id` doesn't exist in `documents` (all actions), or when called with `repair` against a row whose `row_id` is already populated (i.e., not a link-missing orphan). Catch by class; the exception carries `index_id` and `reason` attributes.
- `ValueError` — invalid action, missing `repair_row_id`, unregistered target store, or `repair_row_id` not present in the target table.

## Audit trail

Every action writes a row to `~/.memex/audits/reconciliation-log.md` (`delete-index`, `repair`, `note`). Reverse-orphan `reindex` is deferred.

## Returns

```python
{"action": "<action>", "index_id": "<id>", "result": "<removed|linked|logged>", ...}
```

`repair` additionally returns `"row_id": "<repaired_row_id>"`.

## Implementation

`scripts/agents/data_steward.py:reconcile_orphan()`. Reverse-orphan `reindex` raises `NotImplementedError` until Plan 4 re-embedding tooling lands.
