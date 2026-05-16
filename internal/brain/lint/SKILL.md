---
name: memex:brain:lint
description: Run a Data Steward audit over your Brain. Detects orphans (index entries without matching article/capture/synthesis rows), broken relations, and integrity drift. Read-only; reports findings; does not auto-fix.
---

# memex:brain:lint

## When to use

Periodic maintenance. Recommended monthly or after bulk activity.

## Inputs

None.

## What happens

Invokes `memex:steward:audit`, scoped (in this v2.0 implementation) to the full Index. Returns the report path.

## Invocation

`scripts/brain.py:lint()`
