---
name: memex:index:write
description: Direct write to the federated Index — the lower-level primitive that memex:brain:ingest and memex:brain:capture build on. Use when a consumer (Atelier, custom plugin) needs to add a document to its own store and have it indexed by the Librarian, without going through the Brain layer. Routes through Librarian subagent + Memex Core.
---

# memex:index:write

## When to use

A consumer outside Brain needs to add a document to a store of its own (e.g., Atelier adding a decision to its `decisions` table) and wants the document indexed so that `memex:index:search` (and `memex:brain:ask`) can find it across stores.

Brain's `ingest` and `capture` are convenience wrappers around this skill — they share the same write path but bundle Brain-specific concerns (source-hash dedup, raw archive, article.db schema). Use those for personal Brain content; use this skill for everything else.

## Inputs

- `target_store` — registered store name (e.g., `atelier-projectX`)
- `target_table` — table within that store (must include an `index_id` column)
- `payload` — dict of column values to insert (do NOT include `index_id` — the Librarian assigns it)
- `caller_agent_id` — registered agent id of the writer

## Recipe (Option-B Task-tool dispatch)

### Step 1 — Build the Librarian prompt

```python
from scripts.agents import librarian
prompt = librarian.build_prompt(
    payload=payload,
    target_store=target_store,
    caller_agent_id=caller_agent_id,
)
```

`build_prompt` fetches the `librarian-1` profile + recent index snippet and assembles the full subagent prompt via the `prompts/librarian.md` template.

### Step 2 — Dispatch the Librarian subagent

Use the **Task tool**:

- `subagent_type`: `general-purpose`
- `description`: `Librarian: classify document`
- `prompt`: the value from Step 1

The subagent's final message: JSON with `index_id`, `key`, `domain`, `searchable`, plus optional `metadata`, `relations`.

### Step 3 — Parse and validate

```python
librarian_output = librarian.parse_response(subagent_response)
```

Retry Step 2 once on `ValueError`. After two failures, report `BLOCKED` and stop.

### Step 4 — Encode embedding (optional)

```python
from scripts import embeddings
try:
    embedding = embeddings.encode(librarian_output["searchable"])
except Exception as e:
    print(f"warn: embedding skipped ({e})")
    embedding = None
```

### Step 5 — Persist

```python
result = librarian.write_entry(
    payload=payload,
    librarian_output=librarian_output,
    target_store=target_store,
    target_table=target_table,
    caller_agent_id=caller_agent_id,
    embedding=embedding,
)
```

Returns the dict with `index_id`, `key`, `domain`, `row_id`, `relations`.

## Atomicity contract

Per spec §6.1, the Index write commits BEFORE the target-store write. If the target write fails, an orphan exists in `index.db.documents` until the Data Steward audit catches it. The skill does NOT retry the target-store write — that's manual recovery via `memex:steward:reconcile-orphan`.

## Notes

- The target table MUST have an `index_id` column (and ideally `UNIQUE` on it). Tables without one should use `memex:core:insert` directly — they're considered structural/lookup data, not documents.
- If the Librarian subagent picks an `index_id` that already exists in the Index, the INSERT will fail with a UNIQUE constraint error. The subagent's prompt instructs it to generate fresh UUIDs; collisions should be vanishingly rare.
- Consumers that want structured-row metadata not visible to the Librarian should put it in `payload` (which becomes the target-store row) but not in `searchable` (which becomes the Index's FTS5-indexed text). The Librarian sees `payload` to classify; persistence stores the full row.
