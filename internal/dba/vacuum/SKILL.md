---
name: memex:dba:vacuum
description: Run VACUUM on a registered store to reclaim space and defragment. Should be run during maintenance windows, not under live load.
---

# memex:dba:vacuum

## Inputs

- `store_name`

## Invocation

`scripts/agents/dba.py:vacuum(db_path)`
