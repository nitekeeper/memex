---
id: memex:wiki:memex-disk-layer
slug: memex-disk-layer
title: Memex as the disk layer in the LLM OS
synced-at-commit: 4465f3727246b47b71aab3a8255369b0493c0be9
describes-files: []
status: current
tags: [architecture, llm-os, design-principles]
related: [memex:wiki:testable-metric-constraint, memex:wiki:design-for-async-agents]
created: 2026-05-09
updated: 2026-05-09
---

# Memex as the disk layer in the LLM OS

## Summary

The LLM OS framing (Karpathy 2023) positions the context window as RAM and persistent storage as disk. Memex is that disk layer. The paging metaphor is load-bearing: the LLM kernel must selectively page in what it needs, so the disk must be (1) **accurate** — stale pages corrupt the kernel's reasoning; (2) **queryable** — the kernel needs to find the right page fast; (3) **granular** — pages must be small enough to be selectively loaded without flooding the context window. These three properties, not feature completeness, are the acceptance criteria for Memex v0.

## Details

The framing matters because it sets the right acceptance criteria. A project wiki that is comprehensive but stale is worse than a small wiki that is accurate — a stale page actively misleads the kernel. A wiki that is accurate but not queryable requires dumping the entire disk into RAM on every task. A wiki with large, monolithic pages wastes context even when only one section is relevant.

This maps to concrete Memex design choices:
- `synced-at-commit` + `describes-files` → serves **accuracy** (exact staleness, not heuristic)
- SQLite FTS5 + (future) vector search → serves **queryability**
- "write small, link generously" page style → serves **granularity**

The same three properties constrain the self-improvement loop: the loop can only improve pages it can accurately evaluate as stale or current (see `wiki:testable-metric-constraint`).

## Pointers

- `sources/analyzed/2026-05-09-karpathy-llm-os.md` — source of the disk/RAM framing
- `db/README.md` — placeholder for SQLite schema (FTS5 + future vec)

## Open questions

- What is the right page size target? "Small enough to page in selectively" is intuitive but not a number. First real projects will calibrate this.
- Does the disk metaphor break down for very small projects (where dumping the whole wiki into context is fine)? Probably yes — Memex may be overkill for small projects. Design for large ones; degrade gracefully for small.
