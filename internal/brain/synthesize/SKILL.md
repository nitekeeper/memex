---
name: memex:brain:synthesize
description: Produce a cross-document synthesis on a topic. Two subagent dispatches — Synthesizer reads sources + topic and produces prose; Librarian classifies the resulting synthesis. Saved as a new `synthesis` document in ~/.memex/article.db.syntheses with `synthesizes` relations back to the source index_ids.
---

# memex:brain:synthesize

## When to use

The user has multiple sources on a topic (typically the result of a prior `memex:brain:ask`) and wants a unified, citing prose synthesis preserved as a document of its own.

## Inputs

- `topic` — short topic descriptor (string)
- `input_index_ids` — list of source index_ids to synthesize from
- `caller_agent_id` — registered agent id

## Recipe (Option-B Task-tool dispatch — TWO subagent dispatches)

Synthesize is the only Brain flow with two LLM steps:

1. **Synthesizer** subagent reads the sources + topic, produces prose synthesis.
2. **Librarian** subagent reads the synthesis and classifies it as a new document.

The skill orchestrates both dispatches with `librarian.build_prompt` in between.

### Step 1 — Prepare

```python
from scripts import brain
prep = brain.synthesize_prepare(
    topic=topic,
    input_index_ids=input_index_ids,
    caller_agent_id=caller_agent_id,
)
```

If `prep["sources"]` is empty (none of the input_index_ids matched rows in article.db.articles), report `BLOCKED: no source bodies found for [<ids>]; check the index_ids exist in article.db.articles` and STOP.

Otherwise continue. The prep dict contains the pre-built Synthesizer prompt.

`prep["truncated"]` is `True` when the combined source bodies exceeded `synthesize_prepare`'s `char_budget` (default 32000 chars) and the tail sources were budget-trimmed from the Synthesizer prompt.

### Step 2 — Dispatch the Synthesizer subagent

Use the **Task tool** with:

- `subagent_type`: `general-purpose`
- `description`: `Synthesizer: produce cross-document synthesis`
- `prompt`: `prep["synthesizer_prompt"]`
- `model`: `claude-sonnet-4-6`

> Tier: sonnet (never Opus) — see CLAUDE.md ENFORCED table.

The prompt (template at `prompts/synthesizer.md`) instructs the subagent to produce 2-6 paragraphs of prose with inline `[idx-...]` citations. The subagent's final message is the synthesis text (not JSON — just markdown prose).

Capture the response as `synthesis_body`.

### Step 3 — Build the Librarian prompt for the synthesis

The synthesis is now a new document that needs classifying. Build the Librarian's prompt:

```python
from scripts.agents import librarian
librarian_prompt = librarian.build_prompt(
    payload={
        "topic": prep["topic"],
        "body": synthesis_body,
        "inputs_json": prep["input_index_ids"],
        "created_by": prep["caller_agent_id"],
    },
    target_store="article",
    caller_agent_id=prep["caller_agent_id"],
)
```

### Step 4 — Dispatch the Librarian subagent

Use the **Task tool** with:

- `subagent_type`: `general-purpose`
- `description`: `Librarian: classify synthesis`
- `prompt`: `librarian_prompt`
- `model`: `claude-sonnet-4-6`

> Tier: sonnet (never Opus) — see CLAUDE.md ENFORCED table.

The subagent's final message: JSON with `index_id`, `key`, `domain` (probably `"synthesis"`), `searchable`, optional `metadata`, `relations`.

### Step 5 — Parse and validate

```python
librarian_output = librarian.parse_response(subagent_response)
```

Retry Step 4 once on `ValueError`. After two failures, report BLOCKED. Note: the Synthesizer's output (`synthesis_body`) is already in hand — don't re-run the Synthesizer.

### Step 6 — Encode embedding (optional)

```python
from scripts import embeddings
embedding = embeddings.encode_or_skip(
    librarian_output["searchable"],
    caller_agent_id="synthesizer-1",
    index_id=librarian_output["index_id"],
)
```

### Step 7 — Complete (persist)

```python
result = brain.synthesize_complete(
    prepare_result=prep,
    synthesis_body=synthesis_body,
    librarian_output=librarian_output,
    embedding=embedding,
)
```

`synthesize_complete` automatically appends a `synthesizes` relation for each `input_index_id` (deterministic — we know the inputs by construction). The Librarian's own relations are preserved alongside.

### Step 8 — Report

```
Synthesized to Brain:
  index_id:    <result["index_id"]>
  key:         <result["key"]>
  domain:      <result["domain"]>
  syntheses id:<result["row_id"]>
  sources:     <len(prep["input_index_ids"])>
  relations:   <len(result["relations"])>
```

## Notes

- If a source's body is unavailable (the index_id doesn't resolve in article.db.articles), it's silently dropped from the Synthesizer's input. The skill could check `prep["sources"]` vs `prep["input_index_ids"]` and warn the user if some were missed.
- Embedding skips gracefully without an API key. The synthesis is still FTS5-searchable.
- The two subagent dispatches are sequential, not parallel — the Librarian needs the Synthesizer's output to classify it.
