---
name: memex:core:update
description: Update a single row by integer `id` PK in a registered Memex store. Use for partial updates of non-document rows; document content updates should re-trigger indexing via memex:index:write.
---

# memex:core:update

## Inputs
- `name`, `table`, `row_id`, `updates` (dict)

## Invocation
`scripts/stores.py:update(name, table, row_id, updates)`
