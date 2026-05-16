# CLAUDE.md — entering Memex v0.2

You are operating inside the **Memex product repo**. Memex is Product 1 of Skill Atelier — a personal knowledge runtime and shared memory plane for the agent fleet.

## Architecture in one paragraph

Memex registers a single Claude-Code-visible skill — `memex:run` — which routes natural-language intent (for users) and named operations (for agents) to one of 24 internal procedures at `internal/<category>/<name>/SKILL.md` (categories: `core`, `index`, `brain`, `steward`, `dba`). This keeps the plugin under Claude Code's 1% skill-description budget while exposing the full Memex surface on demand. See `docs/specs/2026-05-16-memex-v2-redesign-design.md` (§8.0) for the visibility model.

## Read at session start (only if you're working ON Memex itself, not USING it)

1. `docs/specs/2026-05-16-memex-v2-redesign-design.md` — v0.2 design
2. `docs/plans/2026-05-16-memex-v2-plan-{1,2,3,4}-*.md` — implementation plans
3. `docs/CORE.md`, `docs/INDEX.md`, `docs/BRAIN.md`, `docs/PACKAGING.md` — per-layer acceptance docs
4. `README.md` and `USER_GUIDE.md` — user-facing entry points
5. `CHANGELOG.md` — version history

If you're a downstream agent USING Memex from another plugin or session, you don't need to read these files — invoke `memex:run` and follow its routing.

## Layer awareness

- This repo is **Layer 2** (a Skill Atelier product). It is not the framework (Layer 1). Do not commit framework-level changes here.
- The framework lives at `C:\Users\user\Documents\Skills\skill-atelier\`.
- Changes to framework files commit there. Changes to Memex files commit here. Never mix.

## Working rules

1. **Spec-first.** v0.2 design is locked in `docs/specs/2026-05-16-memex-v2-redesign-design.md`. Changes to architecture go through a spec revision, not ad-hoc edits.
2. **All writes through the Librarian.** Per spec §6, every document landing in any Memex-managed store must pass through `internal/index/write/` (which routes through the Librarian subagent + Archivist + Memex Core). No bypass paths.
3. **Internal procedures are agent-only.** Don't register additional skills in `plugin.json`; everything goes through `memex:run` routing. New procedures land at `internal/<category>/<name>/SKILL.md` with a corresponding row in `skills/run/SKILL.md`.
4. **Tests are the contract.** Every Python module ships with pytest tests; every SKILL.md ships with a presence/frontmatter test. Run `pytest tests/` before claiming done.
5. **Releases are deliberate.** Use `python -m scripts.release <version>` to build `dist/v<version>/`. Tagging and pushing is a user decision.

## Out-of-scope for v0.2 (do not implement without spec revision)

- Atelier retrofit (Atelier continues to write to its own `.ai/atelier.db`).
- Multi-machine sync / replication.
- Multi-tenant (multiple humans on one install).
- Cross-store ATTACH transactions (current contract: eventually consistent, Data Steward reconciles orphans).
- Re-embedding tooling (one model at a time; backfill deferred).

## When in doubt

Read the spec. If still uncertain, surface it to the user.
