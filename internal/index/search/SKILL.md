---
name: memex:index:search
description: Federated search across every registered Memex store via the Reference Librarian. Lower-level primitive that memex:brain:ask builds on — use directly when a consumer (Atelier, custom plugin) needs raw query results without Brain-specific formatting.
---

# memex:index:search

## When to use

A consumer needs ranked, citation-ready hits from the federated Index without going through Brain. `memex:brain:ask` is a convenience wrapper around this skill that adds user-friendly reporting; use this skill when you want the raw ranked list.

## Inputs

- `query` — natural-language question (string)
- (optional) `caller_agent_id` — defaults to `"reference-librarian-1"` (the Reference Librarian itself acts as the caller for audit purposes)

## Recipe (Option-B Task-tool dispatch)

### Step 1 — Prepare

```python
from scripts.agents import reference_librarian
prep = reference_librarian.ask_prepare(query, caller_agent_id="reference-librarian-1")
```

### Step 2 — Dispatch the Reference Librarian subagent

Use the **Task tool**:

- `subagent_type`: `general-purpose`
- `description`: `Reference Librarian: build query plan`
- `prompt`: `prep["subagent_prompt"]`
- `model`: `claude-haiku-4-5`

> Mechanical query-plan extraction — haiku. (Enforced by `tests/test_model_tier_dispatch.py`.)

Subagent returns a JSON query plan with `fts_query`, `vector_query`, `filters`, `limit`.

### Step 3 — Parse + handle clarification

```python
query_plan = reference_librarian.parse_query_plan(subagent_response)
if "clarify" in query_plan:
    return {"status": "needs_clarification", "question": query_plan["clarify"]}
```

Retry once on parse failure. After two failures, return BLOCKED.

### Step 4 — Execute

```python
from scripts import embeddings
try:
    results = reference_librarian.ask_execute(prep, query_plan, with_embedding=True)
except embeddings.EmbeddingUnavailable as e:
    embeddings.log_skip(
        e,
        caller_agent_id=caller_agent_id,
        input_chars=len(query_plan["vector_query"] or ""),
    )
    results = reference_librarian.ask_execute(prep, query_plan, with_embedding=False)
```

Catches only `EmbeddingUnavailable`; other errors propagate (no silent FTS5-only fallback on real bugs).

Returns a list of dicts: `[{index_id, key, domain, store, table_name, row_id, searchable, embedding}, ...]`. Ordered by relevance.

### Step 5 — Return raw results

This skill does NOT fetch full rows from target stores; the caller decides whether to hydrate. Just return the list from Step 4.

## Notes

- Hybrid retrieval (FTS5 + vector cosine) is attempted by default; the skill falls back to FTS5-only if embedding encoding fails (no API key, provider error, etc.).
- Filters supported: `domain` (e.g., `"article"`, `"decision"`), `store` (e.g., `"article"`, `"atelier-projectX"`). The Reference Librarian decides whether to set them based on the user's question.
- Limit defaults to 10. The subagent can raise it for broad survey queries, lower it for focused lookups.
- Caller's context isolation: same as Librarian — the Reference Librarian's profile and reasoning stay in the subagent's context; the caller's context carries only the parsed plan + results list.
