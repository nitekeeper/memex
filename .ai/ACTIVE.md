---
id: memex:wiki:active
slug: active
title: Memex — current focus
synced-at-commit: 6396be8a1d6e9ff2d908b8678cbd699c755781f0
describes-files: ["ROADMAP.md", "GOALS.md"]
status: draft
tags: [product, active]
created: 2026-05-09
updated: 2026-05-09
---

# Current focus

**Approval queue cleared 2026-05-09.** All eight proposed wiki entries approved and written. Research phase complete.

## Next

1. **Synthesis session** — compose Karpathy + second-brain-blueprint + Superpowers findings into Memex design proposals; resolve format/schema decisions. Key decisions to make:
   - Project-wiki file format (frontmatter fields, body structure)
   - SQLite schema (extends Stage 1 schema; WAL + NORMAL safety required)
   - Skill frontmatter: framework split decision already made (loaded vs. registry)
   - Whether meta-skills get TDD-for-documentation baseline testing before shipping

## Approved wiki entries

From Karpathy ingestion:
- [`wiki:memex-disk-layer`](.ai/wiki/memex-disk-layer.md) — Memex as the disk layer in the LLM OS
- [`wiki:testable-metric-constraint`](.ai/wiki/testable-metric-constraint.md) — improvement loop bounded by measurability
- [`wiki:design-for-async-agents`](.ai/wiki/design-for-async-agents.md) — design for teams of async agents

From second-brain-blueprint ingestion:
- [`wiki:two-tier-instruction-loading`](.ai/wiki/two-tier-instruction-loading.md) — lean root + deferred ops; 86% cold-start reduction
- [`wiki:session-snapshot-format`](.ai/wiki/session-snapshot-format.md) — fixed fields; compression by scope exclusion
- [`wiki:inbox-raw-wiki-pipeline`](.ai/wiki/inbox-raw-wiki-pipeline.md) — raw is immutable; wiki is derived
- [`wiki:approval-gate-with-escape-hatches`](.ai/wiki/approval-gate-with-escape-hatches.md) — gate before every write; hatches narrow the gate
- [`wiki:sqlite-crash-safety`](.ai/wiki/sqlite-crash-safety.md) — WAL + NORMAL; MEMORY + OFF is the crash bug

From Superpowers ingestion:
- [`wiki:skill-cso-description-trap`](.ai/wiki/skill-cso-description-trap.md) — descriptions summarizing workflow shortcircuit the skill body
- [`wiki:mandatory-skill-invocation`](.ai/wiki/mandatory-skill-invocation.md) — 1% rule + anti-rationalization tables
- [`wiki:tdd-for-skill-authoring`](.ai/wiki/tdd-for-skill-authoring.md) — RED-GREEN-REFACTOR for process documentation

## Open items

- DB schema (`db/`) is a stub — populated after synthesis session and format/schema lock.
- `docs/` format specs not yet written — populated after synthesis.

## Pointer

If this entry is stale, compare `synced-at-commit` to repo HEAD; check whether `describes-files` have changed.
