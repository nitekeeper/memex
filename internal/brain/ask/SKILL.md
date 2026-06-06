---
name: memex:brain:ask
description: Ask a natural-language question against the personal Brain. Routes through the Reference Librarian subagent which builds a query plan (FTS5 + optional vector), Python executes against ~/.memex/index.db, fetches full rows from target stores, and returns ranked citation-ready hits.
---

# memex:brain:ask

## When to use

The user wants to find or recall information across their Brain. Replaces v1's wiki/web/training waterfall — v2 trusts the federated Index first.

## Inputs

- `query` — natural-language question (string)
- `mode` — `flat` (default), `global`, or `local` (see "Ask modes" below)

## Ask modes (GraphRAG)

`memex:brain:ask` answers in one of three modes. **`flat` is the default and
its behavior is unchanged** — pick `global`/`local` only when the GraphRAG
community layer has been built (`internal/brain/graph-rebuild/SKILL.md`).

| Mode | Use when | How it answers |
|---|---|---|
| `flat` (default) | A specific lookup/recall | Reference Librarian query plan -> FTS5 + vector cosine over `documents` (Steps 1-5 below). |
| `global` | A corpus-wide / thematic question ("what are the main themes in my Brain?") | Map-reduce over `community_reports` at a level: MAP each report -> scored partial answer (drop zeros), REDUCE sort-desc + budget-fill -> final answer. |
| `local` | An entity/neighborhood question ("what do I know about X and what's near it?") | Seed top docs by cosine, expand the `relations` neighborhood, attach the seeds' community reports, answer over the assembled context. |

Both `global` and `local` depend on the derived layer; if it is empty, run
`internal/brain/graph-rebuild/SKILL.md` first. `global` reports `no_reports` /
`no_signal` and `local` returns empty seeds when the layer/embeddings are
absent — degraded, not an error.

### Global mode recipe (map-reduce over community reports)

```python
from scripts import brain
prep = brain.global_ask_prepare(query, level=0)
if prep["status"] == "no_reports":
    # report "no community reports at level 0 — run graph-rebuild" and STOP
    ...
# MAP: dispatch one general-purpose subagent per unit; parse each:
scored = []
for unit in prep["map_units"]:
    # Task tool: prompt = unit["map_prompt"]; capture <map_response>
    m = brain.parse_map_response(map_response)
    scored.append({"community_id": unit["community_id"], **m})
# REDUCE: drop zeros, sort desc, budget-fill -> reduce prompt
red = brain.global_ask_reduce_prepare(query, scored)
if red["status"] == "no_signal":
    # report "no community is relevant to <query>" and STOP
    ...
# Task tool: prompt = red["reduce_prompt"]; the response is the final answer.
```

### Local mode recipe (neighborhood expansion)

```python
from scripts import brain, embeddings
try:
    ctx = brain.local_ask(query, with_embedding=True)
except embeddings.EmbeddingUnavailable as e:
    embeddings.log_skip(e, caller_agent_id="reference-librarian-1")
    ctx = brain.local_ask(query, with_embedding=False)
# ctx = {seeds, neighborhood, documents:[{index_id, searchable}],
#        community_reports:[{community_id, title, summary}]}
# Assemble documents + community_reports into a single answering prompt and
# dispatch ONE general-purpose subagent to answer the question over them.
```

## Recipe (Option-B Task-tool dispatch) — flat mode

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
