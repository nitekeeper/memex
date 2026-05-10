---
id: memex:wiki:active
slug: active
title: Memex — current focus
synced-at-commit: 6c8e6c31891fca44320fd2652561e07ee9d12db5
describes-files: ["ROADMAP.md", "GOALS.md"]
status: draft
tags: [product, active]
created: 2026-05-09
updated: 2026-05-09
---

# Current focus

**All three research sources ingested 2026-05-09.** Karpathy (3 sources), second-brain-blueprint, and Superpowers (skill system v5.0.7) are all analyzed. Research phase complete.

## Next

1. **Synthesis session** — compose Karpathy + second-brain-blueprint + Superpowers findings into Memex design proposals; resolve format/schema decisions. Key decisions to make:
   - Project-wiki file format (frontmatter fields, body structure)
   - SQLite schema (extends Stage 1 schema; WAL + NORMAL safety required)
   - Skill frontmatter: framework-heavy vs. Superpowers-minimal?
   - Whether SKILL_FORMAT.md adopts DOT graph format conditionally
   - Whether meta-skills get TDD-for-documentation baseline testing

## Wiki entries (approved 2026-05-09)

- [`wiki:memex-disk-layer`](.ai/wiki/memex-disk-layer.md) — Memex as the disk layer in the LLM OS
- [`wiki:testable-metric-constraint`](.ai/wiki/testable-metric-constraint.md) — improvement loop bounded by measurability
- [`wiki:design-for-async-agents`](.ai/wiki/design-for-async-agents.md) — design for teams of async agents

## Wiki proposals from Superpowers ingestion (awaiting approval)

- **skill-cso-description-trap** — descriptions that summarize workflow cause LLMs to skip the skill body; descriptions must state only triggering conditions
- **mandatory-skill-invocation** — the 1% rule as a governance mechanism; anti-rationalization tables as first-class design elements
- **tdd-for-skill-authoring** — baseline scenario (agent without skill) → write skill → re-test; the same RED-GREEN-REFACTOR cycle applied to documentation

## Open items

- DB schema (`db/`) is a stub — populated after synthesis session and format/schema lock.
- `docs/` format specs not yet written — populated after synthesis.
- Approve or reject the three wiki proposals above at synthesis session start.

## Pointer

If this entry is stale, compare `synced-at-commit` to repo HEAD; check whether `describes-files` have changed.
