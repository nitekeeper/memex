---
name: memex:brain:capture
description: Capture a free-form note, observation, or snippet to your Brain. Lighter than ingest — no source URL, no hash check, but still indexed by the Librarian.
---

# memex:brain:capture

## When to use

A thought worth keeping that isn't sourced from elsewhere. Personal observations, working hypotheses, draft snippets.

## Inputs

- `body` — the note text
- `caller_agent_id` — your agent id
- `title` — optional

## What happens

Indexed by Librarian, stored in `article.db.captures`.

## Invocation

`scripts/brain.py:capture(body, caller_agent_id, title)`
