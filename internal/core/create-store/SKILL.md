---
name: memex:core:create-store
description: Create a new Memex-managed SQLite store from a directory of SQL migration files. Use when a consumer (Atelier, Brain, custom) needs a fresh project- or domain-scoped store. Memex creates the file with WAL pragmas, installs the universal migrations table, applies each .sql file in lexical order, and registers the store in the global registry.
---

# memex:core:create-store

## When to use

A consumer needs a new SQLite store provisioned. Typical callers:
- A workspace agent setting up `<repo>/.memex/store.db` for project work.
- An installer seeding a default store like `~/.memex/article.db`.
- A test fixture creating a disposable store.

## Inputs

- `name` — globally unique store name
- `path` — absolute filesystem path for the new SQLite file
- `migrations_dir` — directory containing `.sql` migration files

## Invocation

`scripts/stores.py:create_store(name, path, migrations_dir)`

## Errors

- `ValueError: Store already registered` — pick a different name or use `memex:core:migrate`
- `sqlite3.OperationalError` — invalid migration SQL
