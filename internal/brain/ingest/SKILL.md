---
name: memex:brain:ingest
description: Add an external article or source to your personal Brain. Routes through the Archivist (preserves raw), Librarian (assigns index_id, classifies, links), and Memex Core (writes to article.db). Hash-based rerun safety: re-ingesting the same content is a silent no-op.
---

# memex:brain:ingest

## When to use

You read something worth keeping — an article, a blog post, a paper, a clipped page — and want it findable in your personal Brain. Daily second-brain action.

## Inputs

- `title` — article title
- `body` — article body text (markdown preferred)
- `source_url` — optional; original URL for provenance
- `caller_agent_id` — your registered human agent id (set during onboarding)

## What happens

1. Onboarding check: if no human agent registered, prompts you. Once.
2. Source-hash check: if the canonical body matches an already-ingested article, returns `{"status": "skipped", "existing_index_id": ...}` with no further work.
3. Archivist writes raw body to `~/.memex/raw/`.
4. Librarian indexes (assigns index_id, classifies domain, extracts relations to prior articles).
5. Memex Core inserts a row in `article.db.articles` with `index_id`, `source_hash`, and `raw_path`.
6. Returns `{"status": "ingested", "index_id": ..., "key": ..., "domain": ..., "relations": [...]}`.

## Invocation

`scripts/brain.py:ingest(title, body, caller_agent_id, source_url)`

## Onboarding

If `caller_agent_id` is not registered:
- Prompt: "What's your agent id? (e.g., `human-user`)"
- Prompt: "Display name?"
- Prompt: "Role? (default: User; can be Researcher, Owner, Editor, or custom)"
- Calls `scripts/onboarding.py:register_human()`, then retries the ingest.
