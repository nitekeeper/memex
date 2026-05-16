---
name: memex:index:write
description: Submit a document for centralized indexing by the Memex Librarian, then persist to the target store. This is the MANDATORY write path for all documents — never write directly to a store's document table. Returns the assigned index_id, key, domain, and relations.
---

# memex:index:write

## When to use

Any document — article, decision, meeting, spec, plan, capture, synthesis — that should be findable later. If the row carries an `index_id` column, it MUST go through this skill.

## Inputs

- `payload` — dict containing the document fields (title, body, etc.)
- `target_store` — registered store name (e.g., `article`, `atelier-projectX`)
- `target_table` — table within the target store
- `caller_agent_id` — the registered agent making the write (for attribution)

## What happens

1. Archivist writes the raw payload to `~/.memex/raw/` (content-addressable, idempotent).
2. Librarian (LLM subagent) reads payload + existing index snippet, decides `index_id`, `key`, `domain`, `searchable`, `metadata`, `relations`.
3. Embedding is computed for `searchable` and packed into a BLOB.
4. Index row + relations rows are written to `~/.memex/index.db` (COMMIT).
5. Target store row is written via Memex Core with `index_id` populated (separate COMMIT — eventually consistent, see spec §6.1).
6. Returns: `{index_id, key, domain, relations, row_id}`.

## Invocation

`scripts/agents/librarian.py:index_write(payload, target_store, target_table, caller_agent_id)`

## Errors

- `ValueError: Unknown store` — `target_store` not registered.
- `IntegrityError` — duplicate `index_id` (rare; LLM should generate unique).
- `ValueError: Agent not registered` — `caller_agent_id` not in agents.db.

## Atomicity contract

Index write commits BEFORE target store write. If the target store write fails, the Index row exists without a corresponding store row — an orphan. The Data Steward's next audit will detect and report it. See spec §6.1.
