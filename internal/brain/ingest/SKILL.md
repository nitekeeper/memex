---
name: memex:brain:ingest
description: Ingest an article or external source into the personal Brain (~/.memex/article.db). Routes through Archivist (preserves raw), Librarian subagent (classifies + assigns index_id, relations), and Memex Core (persists). Hash-based rerun safety — re-ingesting the same canonical content is a silent skip.
---

# memex:brain:ingest

## When to use

The user has an article, blog post, paper, clipped page, or other external source they want preserved in their personal Brain.

## Inputs

- `title` — article title (string)
- `body` — full content (markdown preferred)
- `caller_agent_id` — registered agent id (typically the human's id from onboarding)
- `source_url` — optional; original URL for provenance

## Recipe (Option-B Task-tool dispatch)

The Librarian is a Claude Code subagent dispatched via the Task tool. This skill's job is orchestration:

### Step 1 — Prepare

Call Python:

```python
from scripts import brain
prep = brain.ingest_prepare(
    title=title,
    body=body,
    caller_agent_id=caller_agent_id,
    source_url=source_url,  # may be None
)
```

Branch on `prep["status"]`:

- `"skipped"` → the source_hash matches an existing article. Report to the user: `Already ingested as <prep["existing_index_id"]>; no changes.` and STOP. No subagent dispatch, no writes.
- `"ready"` → continue to Step 2. The prep result contains the pre-built Librarian subagent prompt and the payload to persist.

### Step 2 — Dispatch the Librarian subagent

Use the **Task tool** with:

- `subagent_type`: `general-purpose`
- `description`: `Librarian: classify document`
- `prompt`: `prep["subagent_prompt"]`
- `model`: `claude-sonnet-4-6`

> sonnet — bounded payload, never the default Opus. (Enforced by `tests/test_model_tier_dispatch.py`.)

The prompt embedded in `prep["subagent_prompt"]` already contains:
- The Librarian agent's full profile (Dr. Lakshmi Iyer-Ranganathan, faceted classification, etc.) — this becomes the subagent's operating context
- The recent index snippet for cross-reference context
- The payload to classify
- The strict JSON output schema the subagent must follow

The subagent's final message must be a JSON object with `index_id`, `key`, `domain`, `searchable`, and optional `metadata` + `relations`.

### Step 3 — Parse and validate

Call Python:

```python
from scripts.agents import librarian
librarian_output = librarian.parse_response(subagent_response)
```

If `parse_response` raises `ValueError` (the subagent returned malformed JSON or omitted required fields), **retry Step 2 once** with the same prompt. If the second attempt also fails, report `BLOCKED: librarian returned invalid output (sample: <first 200 chars>)` and STOP. No DB writes.

### Step 4 — Encode embedding (optional; graceful degradation)

Call Python:

```python
from scripts import embeddings
embedding = embeddings.encode_or_skip(
    librarian_output["searchable"],
    caller_agent_id="brain-ingest",
    index_id=librarian_output["index_id"],
)
```

### Step 5 — Complete (persist)

Call Python:

```python
result = brain.ingest_complete(prep, librarian_output, embedding=embedding)
```

This writes:
- `~/.memex/index.db.documents` (with `embedding` or NULL)
- `~/.memex/index.db.relations` (rows from `librarian_output["relations"]`)
- `~/.memex/article.db.articles` (the article row, via Memex Core)
- Updates `documents.row_id` with the article's PK

### Step 6 — Report to user

```
Ingested into Brain:
  index_id:   <result["index_id"]>
  key:        <result["key"]>
  domain:     <result["domain"]>
  article id: <result["row_id"]>
  relations:  <len(result["relations"])>
```

## Errors

- `MemexNotInitializedError` → Memex is not bootstrapped. Re-invoke `memex:run`; Step 0 will prompt to bootstrap. If Step 0 is unreachable, run `python3 -m scripts.install` manually.
- `ValueError: Unknown store: article` → `article.db` is missing from `~/.memex/registry.json`. This indicates a partial install — re-invoke `memex:run` so Step 0 detects the missing path, or rerun `python3 -m scripts.install`.
- `ValueError: librarian_output missing fields` → subagent returned bad JSON twice; report BLOCKED.

## Notes

- Embedding is best-effort; without an embedding the document is still findable via FTS5 (just not via vector cosine).
- Source-hash check happens in Step 1 before any subagent dispatch — silent rerun of identical content costs nothing.
