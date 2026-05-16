---
name: memex:dba:integrity-check
description: Run PRAGMA integrity_check on a registered store. Returns 'ok' if clean, otherwise a string describing issues.
---

# memex:dba:integrity-check

## Inputs

- `store_name`

## Invocation

`scripts/agents/dba.py:integrity_check(db_path)`
