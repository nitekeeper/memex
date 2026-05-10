---
id: memex:wiki:design-for-async-agents
slug: design-for-async-agents
title: Design for teams of async agents, not single sessions
synced-at-commit: 4465f3727246b47b71aab3a8255369b0493c0be9
describes-files: []
status: current
tags: [architecture, multi-agent, concurrency, design-principles]
related: [memex:wiki:memex-disk-layer, memex:wiki:testable-metric-constraint]
created: 2026-05-09
updated: 2026-05-09
---

# Design for teams of async agents, not single sessions

## Summary

Karpathy's "research community of agents collaborating asynchronously" (AutoResearch, 2026) is where AI-assisted development is heading. A project wiki designed for one agent in one session will break when two agents run in parallel or when a new agent picks up where another left off. Pages must have stable IDs (agent A's reference survives agent B's update), updates must be atomic (no partial-write corruption), and the staleness signal must be git-based (the only ground truth shared across agents). Memex's `synced-at-commit` + `describes-files` design already satisfies this — but it must stay that way under future pressure to add "simpler" heuristic staleness checks.

## Details

The single-session assumption is a trap. It feels adequate during early development (when one human + one AI works on one thing at a time) but breaks at the first real use case: two agents working on different parts of a codebase simultaneously, or an agent picking up a task that another agent started and didn't finish.

The git-based staleness signal is not just elegant — it is the only shared ground truth that survives context loss, agent restarts, and parallel work. A heuristic like "updated more than N days ago" fails as soon as the codebase is updated by an agent that doesn't update the page timestamp. `synced-at-commit` fails only if git history is rewritten, which is a much stronger guarantee.

Stable IDs (namespaced slugs per `docs/PROJECT_WIKI_FORMAT.md`) matter for the same reason: an agent referencing `memex:wiki:memex-disk-layer` must get the same page regardless of when or by whom the page was last edited.

**Do not add heuristic staleness checks** (time-based, line-count-based, etc.) as shortcuts. They feel simpler but undermine the shared ground truth property.

## Pointers

- `sources/analyzed/2026-05-09-karpathy-autoresearch.md` — "research community of agents collaborating asynchronously"
- `docs/PROJECT_WIKI_FORMAT.md` (Skill Atelier) — `synced-at-commit` + `describes-files` spec

## Open questions

- When two agents update the same page concurrently, how is the conflict resolved? Git merge conflict on a markdown file. Is this acceptable, or does Memex need a locking mechanism?
- Does the "team of agents" assumption require a shared SQLite database? If so, concurrent writes to SQLite need WAL mode at minimum. Flag this for the db schema design.
