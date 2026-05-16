---
name: memex:core:delete
description: Delete a row by integer `id` PK from a registered Memex store. Returns true if a row was deleted, false otherwise. Document deletes should also notify the Librarian (deferred to Plan 2).
---

# memex:core:delete

## Inputs
- `name`, `table`, `row_id`

## Invocation
`scripts/stores.py:delete(name, table, row_id)`
