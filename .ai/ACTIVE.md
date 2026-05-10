---
id: memex:wiki:active
slug: active
title: Memex — current focus
synced-at-commit: 4803941c2cdfc137ecb4876bb0eb706454320448
describes-files: ["ROADMAP.md", "GOALS.md"]
status: draft
tags: [product, active]
created: 2026-05-09
updated: 2026-05-09
---

# Current focus

**Karpathy ingested 2026-05-09.** Three sources analyzed: Software 2.0, LLM OS, AutoResearch. Key themes extracted. Wiki entry proposals queued.

## Next

1. **Ingest user's existing LLM wiki build** — concrete prior art; most actionable input. Most direct influence on Memex's format decisions.
2. **Ingest Superpowers** — deliberately last to avoid cargo-cult.
3. **Synthesis session** — compose findings into design proposals, resolve format/schema decisions.

## Pending wiki entry proposals (from Karpathy ingestion)

- `wiki:memex-disk-layer` — Memex as the "disk" in the LLM OS; accuracy/queryability/granularity as the three load-bearing properties
- `wiki:testable-metric-constraint` — improvement loop bounded by measurability; staleness is v0's signal
- `wiki:design-for-async-agents` — project wikis serve teams of agents, not single sessions

These are proposals. Approve or discard at session close.

## Open items

- DB schema (`db/`) is a stub — populated after synthesis session and format/schema lock.
- `docs/` format specs not yet written — populated after synthesis.

## Pointer

If this entry is stale, compare `synced-at-commit` to repo HEAD; check whether `describes-files` have changed.
