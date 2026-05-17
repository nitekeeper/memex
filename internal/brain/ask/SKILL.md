---
name: memex:brain:ask
description: Ask a natural-language question against the personal Brain. Routes through the Reference Librarian subagent which builds a query plan (FTS5 + optional vector), Python executes against ~/.memex/index.db, fetches full rows from target stores, and returns ranked citation-ready hits.
---

# memex:brain:ask

## When to use

The user wants to find or recall information across their Brain. Replaces v1's wiki/web/training waterfall — v2 trusts the federated Index first.

## Inputs

- `query` — natural-language question (string)

## Recipe (Option-B Task-tool dispatch)

The Reference Librarian is a Claude Code subagent dispatched via the Task tool. Its job is to translate the user's question into a structured query plan; Python executes the plan.

### Step 1 — Prepare

```python
from scripts import brain
prep = brain.ask_prepare(query)
```

Returns `{"status": "ready", "query": ..., "subagent_prompt": ..., ...}`. The prompt embeds Dr. Eleanor Whitfield's full profile + the user's query.

### Step 2 — Dispatch the Reference Librarian subagent

Use the **Task tool** with:

- `subagent_type`: `general-purpose`
- `description`: `Reference Librarian: build query plan`
- `prompt`: `prep["subagent_prompt"]`

The subagent's final message must be a JSON object with these fields:

```json
{
  "fts_query":    "<FTS5 MATCH expression>",
  "vector_query": "<text to embed for cosine, or null to skip>",
  "filters":      {"domain": "<optional>", "store": "<optional>"},
  "limit":        10
}
```

If the user's query is genuinely ambiguous, the subagent may return `{"clarify": "<one short question>"}` instead — report that to the user and STOP (no DB read).

### Step 3 — Parse the query plan

```python
from scripts.agents import reference_librarian
query_plan = reference_librarian.parse_query_plan(subagent_response)
```

If the plan contains a `"clarify"` key, report the clarifying question and STOP. Otherwise continue.

If `parse_query_plan` raises (subagent returned invalid JSON), retry Step 2 once. After two failures, report `BLOCKED: reference librarian returned invalid plan` and STOP.

### Step 4 — Execute the plan

Attempt hybrid retrieval (FTS5 + vector cosine). If the embedding
provider is unavailable, log the skip and fall back to FTS5-only.
`ask_execute` internally guards against a null `vector_query` field, so
no sentinel check is needed here.

```python
from scripts import embeddings
try:
    results = brain.ask_execute(prep, query_plan, with_embedding=bool(query_plan.get("vector_query")))
except embeddings.EmbeddingUnavailable as e:
    embeddings.log_skip(
        e,
        caller_agent_id="reference-librarian-1",
        input_chars=len(query_plan.get("vector_query") or ""),
    )
    results = brain.ask_execute(prep, query_plan, with_embedding=False)
```

Catching only `EmbeddingUnavailable` lets unrelated failures (parse
errors, missing fields) propagate as real bugs.

### Step 5 — Fetch full rows + report

Each result row from `ask_execute` carries `index_id`, `key`, `domain`, `store`, `table_name`, `row_id`, `searchable`. For full body content, fetch from the target store via Core:

```python
from scripts import stores
for r in results:
    rows = stores.query(r["store"], f"SELECT * FROM {r['table_name']} WHERE id = ?", (r["row_id"],))
    if rows:
        r["full_row"] = rows[0]
    else:
        # Transient orphan: index has the row, target store doesn't.
        # Log + skip from output; Data Steward will catch it next audit.
        r["_skip"] = True
```

Report to the user:

```
Found N results for "<query>":
  1. [<domain>] <key>   (store=<store>)
     <searchable preview, first 200 chars>
  2. ...
```

If results is empty, report `No matches in your Brain for "<query>". Try a web search, or ingest more sources.`

## Notes

- Default behavior: hybrid retrieval (FTS5 + vector) when an embedding API key is configured; FTS5-only otherwise. The skill handles the fallback automatically.
- Cross-store search: this skill queries every registered store via the federated Index, not just `article.db`. A question may surface results from Atelier's decisions table, meeting minutes, etc., as long as those rows were indexed via the Librarian.
- Caller's context only carries the parsed query plan + final results. The Reference Librarian's profile and the rest of its reasoning stay in the subagent's context.
