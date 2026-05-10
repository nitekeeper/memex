---
id: memex:wiki:digest
slug: digest
title: Memex — project digest
synced-at-commit: d5bc084b0383aea3e7f63a39d91052bc2db9e0a4
describes-files: ["README.md", "GOALS.md", "ROADMAP.md", "DESIGN_NOTES.md"]
status: draft
tags: [product, digest]
created: 2026-05-09
updated: 2026-05-09
---

# Memex — project digest

> Product 1 of Skill Atelier. A project-wiki capability for AI systems with exact git-anchored staleness semantics and a self-improvement loop.

## What this project is

Memex gives AI systems structured, persistent knowledge of any project they work in. Wiki pages track which files they describe and which commit they were last synced against — staleness is exact, not heuristic. A self-improvement loop (lesson capture/review, wiki curation) lives alongside the wiki capability.

Named for Vannevar Bush's 1945 memory-extender concept.

## Where it lives

`C:\Users\user\Documents\Skills\memex\`

## Key files

- [`README.md`](../README.md) — entry point
- [`CLAUDE.md`](../CLAUDE.md) — AI session operating rules
- [`GOALS.md`](../GOALS.md) — north-star, current focus, anti-goals
- [`ROADMAP.md`](../ROADMAP.md) — what's done, what's next
- [`DESIGN_NOTES.md`](../DESIGN_NOTES.md) — decisions log
- [`sources/`](../sources/) — research materials (inbox, analyzed)
- [`skills/`](../skills/) — the skill files (populated in build phase)
- [`docs/`](../docs/) — format specs (populated after synthesis)
- [`dist/`](../dist/) — released artifacts (none yet)

## Current state

Research phase. Repo scaffolded 2026-05-09. No sources ingested yet. First source: Karpathy's writings on self-improvement and LLM-as-OS.

## Relationship to Skill Atelier

Skill Atelier dogfoods Memex throughout development. Each working version of Memex replaces more of Skill Atelier's rough `.ai/` and `wiki/` tooling. Skill Atelier is the most demanding user of Memex before any external consumer sees it.
