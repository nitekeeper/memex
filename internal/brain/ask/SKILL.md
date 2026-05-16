---
name: memex:brain:ask
description: Ask a natural-language question against your Brain. Routes through the Reference Librarian which decomposes the query, runs FTS5 + vector retrieval across the Index, ranks results, and returns citation-ready hits with full content fetched from target stores.
---

# memex:brain:ask

## When to use

You want to find or remember something. Replaces v1 blueprint's wiki/web/training waterfall — Brain trusts the Index first; web fallback is the caller's responsibility (Brain does not auto-search the web in v0.2).

## Inputs

- `query` — natural-language question

## What happens

1. Reference Librarian builds an FTS5 + vector query plan.
2. Plan executes against `~/.memex/index.db`.
3. Top candidates' full rows are fetched from their target stores.
4. Returns ranked list with provenance.

## Invocation

`scripts/brain.py:ask(query)`

## Output

```json
[
  {
    "index_id": "...",
    "store": "article",
    "key": "...",
    "domain": "article",
    "title": "...",
    "body": "...",
    "relevance": 0.83
  },
  ...
]
```
