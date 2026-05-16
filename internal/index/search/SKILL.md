---
name: memex:index:search
description: Ask the Memex Reference Librarian a natural-language question. Returns a ranked list of relevant documents across every registered store, with full content fetched from target stores. Replaces direct querying of any single store for read operations.
---

# memex:index:search

## When to use

Any read where the answer might span multiple stores, or where the caller doesn't know which store holds the relevant content. Brain's `ask` skill wraps this directly. Atelier or any consumer can also invoke it.

## Inputs

- `query` — natural-language question
- (optional) `filters` — dict, e.g., `{"domain": "article", "store": "brain"}` to constrain
- (optional) `limit` — max results (default 10)

## What happens

1. Reference Librarian (LLM subagent) parses the query, builds an FTS5 + vector query plan.
2. Plan executes against `~/.memex/index.db`.
3. Top N candidate `index_id`s are returned.
4. For each candidate, the target row is fetched from its store via Core.
5. If a row fetch fails (transient orphan), it is logged + skipped. Data Steward is notified asynchronously.
6. Returns ranked list of dicts: `[{index_id, store, key, domain, body, relevance, ...}, ...]`.

## Invocation

`scripts/agents/reference_librarian.py:ask(query)`

## Notes

- Hybrid retrieval (FTS5 + vector cosine) is used when embeddings are present. In v2.0, embeddings are computed on write; backfill is not yet implemented (see Plan 4 for re-embed tooling).
