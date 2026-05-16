---
name: memex:core:migrate
description: Apply additional SQL migration files to an existing Memex-managed store. Idempotent — already-applied migrations (tracked in the store's `migrations` table) are skipped. Use when a consumer's schema evolves and new .sql files need to be applied to an in-place store without recreating it.
---

# memex:core:migrate

## Inputs
- `name` — registered store name
- `migrations_dir` — directory containing `.sql` files

## Invocation
`scripts/stores.py:migrate(name, migrations_dir)`

## Errors
- `ValueError: Unknown store` — `name` is not registered
