---
name: memex:steward:audit-store
description: Run an integrity audit scoped to a single registered store (reverse orphans + schema drift). Lighter than full audit.
---

# memex:steward:audit-store

## Inputs

- `store_name` — registered store to audit
- `table` — table within the store to scan for reverse orphans

## Invocation

`scripts/agents/data_steward.py:find_reverse_orphans(index_db_path, store_name, table)`
