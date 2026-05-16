---
name: memex:core:register-role
description: Register a new role in the global agents.db roles table. Roles are universal (Memex-managed schema, multi-tenant rows). Consumers (Atelier, future plugins) call this on install to seed their own role taxonomies.
---

# memex:core:register-role

## Inputs
- `name` — role name (UNIQUE)
- `description` — short description

## Invocation
`scripts/roles.py:create_role(db_path, name, description)` where `db_path` is `~/.memex/agents.db`
