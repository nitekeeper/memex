---
id: source:second-brain-blueprint
slug: second-brain-blueprint
title: Second Brain Blueprint — nitekeeper/second-brain-blueprint
type: repo
authors: [nitekeeper]
url: "https://github.com/nitekeeper/second-brain-blueprint"
captured: 2026-05-09
status: analyzed
relevance-to: [memex]
tags: [llm-wiki, project-wiki, persistent-knowledge, session-memory, obsidian, sqlite, cold-start]
informs-decisions: []
---

# Second Brain Blueprint

## Summary

Second Brain Blueprint is a working implementation of the Karpathy "LLM Wiki" pattern: an AI agent (Claude) maintains a persistent, compounding wiki in a local Obsidian vault, building interconnected markdown pages from ingested sources rather than re-deriving answers from scratch. The repo ships as a blueprint that users clone and run a setup guide to deploy their own instance. It is the closest concrete prior art to Memex — a real system used in production, not just a design sketch, shaped by multiple audit cycles that are visible in the git history.

## Key claims

- **Two-tier instruction loading reduces cold-start cost by 86%**: a lean `CLAUDE.md` (~1,000–2,100 tokens always loaded) defers heavy ops content (session memory, blueprint sync, reference) to files that load only when triggered. This is the primary architectural insight.
- **Query routing is a strict waterfall**: wiki-first → web search → training knowledge. No ambiguous judgment calls; the order is deterministic and the agent never skips tiers.
- **Approval-before-write is non-negotiable**: the agent shows a plan and token estimate before any file change, with documented exceptions only for `!! wrap` and `!! ready` which have their own safeguards.
- **Session memory is a structured snapshot, not prose**: the `[SNAPSHOT]` format has six fixed fields (TASK, STATE, NEXT, LOCKED, FILES, WATCH). The compression mechanism is scope exclusion (drop resolved/wiki content), not a character limit.
- **Inbox → raw → wiki pipeline**: web-clipped articles land in `inbox/`, agent moves them to `raw/` as an immutable archive, wiki pages are derived artifacts. The source is never overwritten.
- **SQLite is an optional skill, not a core dependency**: FTS5 is offered at setup time and gated behind a Python availability check; the system degrades gracefully without it.
- **Python replaces Bash for cross-platform ops**: `wrap.py`, `ready.py`, `estimate_tokens.py`, and `check_deps.py` — avoiding shell portability issues. The resolved Python command is stored in `hot.md` at setup time.
- **`hot.md` tracks live state**: after every state-changing operation (`ingest`, `lint`, `audit`) the agent updates `hot.md`, making it a lightweight freshness signal. `log.md` provides the full audit trail.
- **Token budget is explicit**: the agent estimates token cost before every write; typical operations range from ~1,500 tokens (wrap) to ~45,000 tokens (full audit). Session hygiene (wrap + fresh session) is advised after heavy operations.
- **Confidence scoring for training-knowledge fallback**: answers from training knowledge include "Confidence: N/10 — [caveat]" at every confidence level except 8–10 on timeless topics.

## Relevance

This source directly informs the following Memex open questions:

**Format decisions**: The two-tier loading model (lean root file + deferred ops) is a proven pattern for keeping cold-start costs low. Memex should consider the same split — a lean `CLAUDE.md`-equivalent plus deferred skill content.

**Session-memory schema**: The `[SNAPSHOT]` format (TASK / STATE / NEXT / LOCKED / FILES / WATCH) is a concrete, field-tested design for cross-session context preservation. Memex's `capture` skill should evaluate this format vs. alternatives.

**Staleness detection**: `hot.md` as a live-state file and `log.md` as audit trail are analogous to Memex's `synced-at-commit` principle, but implemented via append-on-write rather than git metadata. The two approaches are complementary, not competing.

**Approval gate**: The approval-before-write pattern with token estimates is exactly the guard Memex needs for its `capture` skill. The exception pattern (`!! wrap` / `!! ready` with built-in safeguards) shows how to provide escape hatches without abandoning the gate.

**Inbox pipeline**: The `inbox/ → raw/ → wiki/` flow is a direct model for Memex's ingest path. "Raw is immutable; wiki is derived" is a principle Memex should adopt verbatim.

**SQLite FTS**: Validates that Python + SQLite (standard library) is a viable FTS approach with no infrastructure dependency. The optional-skill pattern also shows how to gate advanced features.

**Query routing**: The deterministic waterfall (wiki → web → training) is directly applicable to Memex's `search` skill. The confidence-score requirement for training-knowledge answers is a transparency mechanism worth adopting.

**Scope**: This repo is Obsidian-centric (personal vault, local files). Memex should note that it is not trying to replicate Obsidian integration — it is trying to extract the agent-side patterns. The Obsidian coupling is implementation detail, not the insight.

## Open questions

- The blueprint uses a flat `wiki/` directory with subfolders by topic. Memex's project-wiki concept is per-project, not personal. How should the folder schema differ when the wiki describes a *codebase* rather than a *personal knowledge base*?
- `hot.md` is updated by the agent after every state change. In Memex, staleness is tracked via `synced-at-commit` (git-derived). Can these coexist, or does one make the other redundant?
- The approval gate works well for a single-user interactive session. Memex will be used inside multi-turn development sessions where the agent may need to write many wiki pages in one pass. Does the per-write approval model survive batch capture?
- The blueprint defers ops content to separate files loaded on demand. In Memex's Skill format, the analogous mechanism is skill files themselves. Do we need an additional deferred-loading layer, or is the Skill boundary sufficient?
- The `graphiti-query` skill (temporal knowledge graph via Zep/Graphiti) is on the blueprint's roadmap. Memex's planned `search` skill uses SQLite FTS5. Are these complementary or is one strictly better for the project-wiki use case?
- The blueprint's Python scripts are cross-platform by design. Memex currently assumes Windows (PowerShell environment). Should Memex also target cross-platform from v0, or defer?

## Excerpts

> "Knowledge builds over time instead of being re-derived on every question." — README

> "Cold-start tokens drop from ~7,780 to ~1,080. Write operations gain ~2,120 tokens by eliminating `token-reference.md` reads." — cold-start-optimization-design.md

> "The filter (exclude resolved/wiki content) is the only compression mechanism." — wrap-compact-redesign.md (on session snapshot compression)

> "Same input → zero state change." — user-guide.md (on the hash-check deduplication guarantee)

> "All critical state is in files on disk." — user-guide.md (justifying fresh-session-after-heavy-ops advice)
