---
name: memex:brain:capture
description: Capture a free-form note or observation into the personal Brain (~/.memex/article.db.captures). Lighter than ingest — no source URL, no raw archive, but still routed through the Librarian subagent for classification and linking.
---

# memex:brain:capture

## When to use

The user wants to record a thought, observation, or short snippet that isn't sourced from elsewhere. No URL, no provenance — just a note that should be findable later.

## Inputs

- `body` — the note text
- `caller_agent_id` — registered agent id
- `title` — optional short label

## Recipe (Option-B Task-tool dispatch)

### Step 1 — Prepare

```python
from scripts import brain
prep = brain.capture_prepare(
    body=body,
    caller_agent_id=caller_agent_id,
    title=title,  # may be None
)
```

`prep["status"]` is always `"ready"` (no source-hash dedup for captures — every capture is a fresh thought).

### Step 2 — Dispatch the Librarian subagent

Use the **Task tool**:

- `subagent_type`: `general-purpose`
- `description`: `Librarian: classify capture`
- `prompt`: `prep["subagent_prompt"]`
- `model`: `claude-sonnet-4-6`

> sonnet — bounded payload, deliberate downshift, never silent. (Enforced by `tests/test_model_tier_dispatch.py`.)

Same Librarian profile + classification policy as ingest; the subagent decides `domain="capture"` (or whatever fits — Librarian's judgment).

### Step 3 — Parse and validate

```python
from scripts.agents import librarian
librarian_output = librarian.parse_response(subagent_response)
```

Retry once on `ValueError`. After two failures, report BLOCKED.

### Step 4 — Encode embedding (optional)

```python
from scripts import embeddings
embedding = embeddings.encode_or_skip(
    librarian_output["searchable"],
    caller_agent_id="brain-capture",
    index_id=librarian_output["index_id"],
)
```

### Step 5 — Complete

```python
result = brain.capture_complete(prep, librarian_output, embedding=embedding)
```

Writes to `~/.memex/article.db.captures` and the Index.

### Step 6 — Report

```
Captured to Brain:
  index_id:   <result["index_id"]>
  key:        <result["key"]>
  domain:     <result["domain"]>
  capture id: <result["row_id"]>
```

## Notes

- Captures and ingests share the same Librarian flow; they only differ in target table (`captures` vs `articles`) and whether the payload includes source-URL/hash fields.
- Captures don't go through Archivist — they're not "sources" with raw originals. The `body` text in `captures` IS the canonical content.
