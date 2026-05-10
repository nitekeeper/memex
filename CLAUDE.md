# CLAUDE.md — entering Memex

You are operating inside the **Memex product repo**. Memex is Product 1 of Skill Atelier. This repo holds the research, design, skill source, and releases for the Memex product.

## Read at session start

1. `GOALS.md` — north-star, current focus, anti-goals.
2. `ROADMAP.md` — what's in flight and what's next.
3. `DESIGN_NOTES.md` — decisions made so far.

## Layer awareness

- **This repo is Layer 2** (a skill product). It is not the framework (Layer 1). Do not commit framework-level changes here.
- The framework lives at `C:\Users\user\Documents\Skills\skill-atelier\`.
- Changes to framework files commit there. Changes to Memex files commit here. Never mix.

## Working rules

1. **Research before design.** No format or schema is locked until sources are ingested and synthesized. See `sources/` for ingestion workflow.
2. **Source everything significant.** When research material informs a decision, it should be in `sources/analyzed/` before the decision is logged.
3. **Capture lessons after meaningful work.** After non-trivial sessions, capture to `lessons/inbox/`.
4. **Propose wiki entries during sessions; approve at session close.** Do not unilaterally edit `.ai/wiki/` mid-flow.
5. **Releases are deliberate.** Do not auto-promote to `dist/`. The release skill (from Skill Atelier's `meta/cut-release/`) is the only path.
6. **Surface conflicts with goals.** If a request conflicts with `GOALS.md`, flag before acting.

## When in doubt

Read `GOALS.md`. Check alignment. If still uncertain, surface it to the user.
