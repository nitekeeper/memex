---
name: memex:core:query
description: Run a SELECT query against any registered Memex store. Returns rows as a list of dicts. Use for read-only operations; for full-text or vector search, use memex:index:search instead.
---

# memex:core:query

## Inputs
- `name` — registered store name
- `sql` — SELECT statement
- `params` — optional tuple of bind parameters

## Invocation
`scripts/stores.py:query(name, sql, params)`
