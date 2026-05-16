---
name: memex:steward:audit
description: Run a full integrity audit across the Memex Index and all registered stores. Detects orphans, broken relations, schema drift. Writes a structured audit report to ~/.memex/audits/. Read-only — never auto-fixes.
---

# memex:steward:audit

## When to use

- Scheduled maintenance (weekly/monthly recommended).
- After bulk operations (large ingests, mass deletes).
- Before a backup, to ensure clean snapshot.

## Inputs

None.

## Behavior

Invokes the Data Steward's audit primitives in sequence: find_orphans, find_broken_relations, retention policy verification (Plan 2 implements orphans + broken relations; retention verification is deferred).

## Invocation

`scripts/agents/data_steward.py:audit(index_db_path)`

Returns: absolute path to the generated report.
