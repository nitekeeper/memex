---
name: memex:index:write
description: Direct write to the federated Index — the lower-level primitive that memex:brain:ingest and memex:brain:capture build on. Use when a consumer (Atelier, custom plugin) needs to add a document to its own store and have it indexed by the Librarian, without going through the Brain layer. Routes through Librarian subagent + Memex Core.
---

# memex:index:write

## When to use

A consumer outside Brain needs to add a document to a store of its own (e.g., Atelier adding a decision to its `decisions` table) and wants the document indexed so that `memex:index:search` (and `memex:brain:ask`) can find it across stores.

Brain's `ingest` and `capture` are convenience wrappers around this skill — they share the same write path but bundle Brain-specific concerns (source-hash dedup, raw archive, article.db schema). Use those for personal Brain content; use this skill for everything else.

## Inputs

- `target_store` — registered store name (e.g., `atelier`)
- `target_table` — table within that store (must include an `index_id` column)
- `payload` — dict of column values to insert (do NOT include `index_id` — the write path assigns it)
- `caller_agent_id` — registered agent id of the writer
- `librarian_output` — **optional** dict. If the caller already knows the classification (typical for consumers writing structured rows like Atelier's `tasks` / `decisions` / `meetings`), supply it directly and the Librarian subagent dispatch is skipped. Schema:

  ```jsonc
  {
    "index_id":  "<uuid>",            // required — unique across the Index
    "key":       "<slug>",            // required — stable human-readable identifier
    "domain":    "<vocabulary term>", // required — e.g. "article" | "task" | "decision"
    "searchable":"<FTS5 text>",       // required — what Index FTS5 indexes
    "metadata":  { ... },             // optional — defaults to {}
    "relations": [{ "to_index_id": "...", "rel_type": "..." }]  // optional — defaults to []
  }
  ```

  When omitted (`None`), the Librarian subagent produces this dict via LLM dispatch. Use the dispatch path for prose ingest where domain and relations need extraction from text; use the caller-built path when those facts are already known.

## Recipe (Option-B Task-tool dispatch)

### Step 0 — Branch on `librarian_output`

- If the caller supplied `librarian_output`, **skip Steps 1–3.** Validate the dict via `scripts.agents.librarian.validate_output(librarian_output)` and proceed to Step 4. On `ValueError`, report `BLOCKED` with the validation error; do not retry.
- If `librarian_output` is `None`, run the full dispatch (Steps 1–3 below).

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
- `model`: `claude-sonnet-4-6`

> This is the M3 single-write-path Librarian — the integrity bottleneck
> guarding the one write path — so it stays at sonnet (NOT haiku) to respect
> the integrity-bottleneck guidance while still killing the silent-Opus
> inheritance; deliberate downshift from the Opus default, never inherited.
> (Enforced by `tests/test_model_tier_dispatch.py`.)

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
except embeddings.EmbeddingUnavailable as e:
    embeddings.log_skip(
        e,
        caller_agent_id=caller_agent_id,
        index_id=librarian_output["index_id"],
        input_chars=len(librarian_output["searchable"]),
    )
    embedding = None
```

Catches only `EmbeddingUnavailable` (degraded-mode signal) — any other
exception propagates so real bugs surface. `log_skip` writes a structured
row to `~/.memex/audits/embedding-skip-log.md`; the FTS5 path is
unaffected by the missing vector.

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
- If the assigned `index_id` already exists in the Index, the INSERT will fail with a UNIQUE constraint error. The subagent's prompt instructs it to generate fresh UUIDs; caller-built dicts should do the same (e.g. `uuid.uuid4()` or `uuid7()`). Collisions should be vanishingly rare.
- Consumers that want structured-row metadata not visible to FTS5 should put it in `payload` (which becomes the target-store row) but keep it out of `searchable` (which becomes the Index's FTS5-indexed text). The Librarian sees `payload` to classify on the dispatch path; persistence stores the full row either way.

## When to use the caller-built `librarian_output` path

Skip the subagent when **all** of the following hold:

- The caller knows the document's `domain` from context (e.g., Atelier writing to its `tasks` table knows the domain is `task`).
- `searchable` can be built deterministically from the structured row (typically `title + body[:N]`).
- Relations are either empty or explicit in the caller's data model (e.g., `task part_of project`). The Librarian's value-add for prose ingest is discovering cross-doc relations from text; for structured-row writers with an explicit graph, caller-built relations are strictly more accurate.

For everything else — articles, transcripts, free-form notes, anything where domain or relations need to be extracted from prose — dispatch the subagent.

Whichever path produced the dict, `librarian.write_entry` is the single write surface. The architectural invariant (no bypass of the Index↔store coupling, Data Steward catches orphans) is preserved either way.

## GraphRAG layer staleness (derived artifacts)

The GraphRAG community layer (`relations` `similar_to` edges, `communities`,
`community_members`, `community_reports`) is DERIVED from `documents` and is
NOT kept live on the write path — recomputing it would put a similarity scan
+ clustering + an LLM call behind every ingest. A new document written here
therefore makes the community layer **stale**: the new node is not yet in the
similarity graph and not yet a member of any community.

Staleness is resolved out-of-band by the operator-run maintenance entry point
`internal/brain/graph-rebuild/SKILL.md` (build graph -> detect communities ->
generate the missing reports). Report generation is incremental
(`community_reporter.stale_community_ids()` returns only report-less
communities), so a rebuild after a batch of ingests is cheap relative to the
ingests themselves. `memex:brain:ask` in `flat` mode does not depend on the
community layer and is always current; `global`/`local` modes read the layer
as last rebuilt.
