---
name: memex:brain:synthesize
description: Produce a cross-document synthesis on a topic. Given a list of source index_ids, the Synthesizer LLM produces a unified prose synthesis with inline citations; the result is indexed as a new `synthesis` document.
---

# memex:brain:synthesize

## When to use

You have multiple sources on a topic and want to see the through-line. Higher-order than `ask` — produces a written synthesis, not just a result list.

## Inputs

- `topic` — short topic descriptor
- `input_index_ids` — list of source index_ids (typically results of a prior `ask`)
- `caller_agent_id`

## What happens

1. Fetches full source bodies from `article.db.articles` for each input index_id.
2. Synthesizer LLM produces prose synthesis with `[idx-...]` citations.
3. Synthesis is stored in `article.db.syntheses` with `inputs_json` recording provenance.
4. Librarian indexes the synthesis as `domain: synthesis` with `synthesizes` relations back to inputs.

## Invocation

`scripts/brain.py:synthesize(topic, input_index_ids, caller_agent_id)`
