---
name: memex:dba:checkpoint
description: Run a WAL checkpoint on a registered store. Mode defaults to PASSIVE.
---

# memex:dba:checkpoint

## Inputs

- `store_name` — registered store
- `mode` — PASSIVE | FULL | RESTART | TRUNCATE (default PASSIVE)

## Invocation

`scripts/agents/dba.py:checkpoint(db_path, mode)`
