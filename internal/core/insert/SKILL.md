---
name: memex:core:insert
description: Insert a row into a table of a registered Memex store. Use for non-document tables (lookup tables, configuration, agents, roles). For document rows that need to be indexed, use memex:index:write instead — that routes through the Librarian.
---

# memex:core:insert

## Inputs
- `name`, `table`, `row` (dict of column → value)

## Invocation
`scripts/stores.py:insert(name, table, row)`
