# CLAUDE.md — entering Memex

You are operating inside the **Memex product repo**. Memex is Product 1 of Skill Atelier. This repo holds the research, design, skill source, and releases for the Memex product.

## Read at session start

1. `GOALS.md` — north-star, current focus, anti-goals.
2. `ROADMAP.md` — what's in flight and what's next.
3. `DESIGN_NOTES.md` — decisions made so far.

## Session start

Before responding to the user's first message, run the self-improvement queue-processing pass:

1. **`review-lessons` (solo)** — scan `lessons/feedback/` then `lessons/inbox/` for `status: draft` lessons.
   - **Promote** if the lesson is factual, self-contained, and has a concrete how-to-apply.
   - **Defer** (leave as draft) if the lesson touches goals, priorities, design philosophy, or contradicts an existing approved wiki entry.
   - **Discard** if it duplicates something already in the wiki or is purely session-local.
   - Apply actions directly — no approval gate.

2. **`propose-wiki-entry` (solo)** — convert all newly promoted lessons into draft wiki entries in `.ai/wiki/`. Apply directly — no approval gate.

3. **`sync`** — run `python scripts/sync.py .ai/` from the Memex product root to surface stale wiki entries.

4. **Show summary** using this exact format:

   ```
   Session-start self-improvement pass — YYYY-MM-DD
     Lessons reviewed: N
       Promoted: X
       Deferred (needs collaborative review): Y
       Discarded: Z
     Wiki entries proposed: M
     Stale entries flagged: K
       - <title> (.ai/wiki/<slug>.md)
   ```

   If nothing was in the queue, show: `Session-start pass — nothing in queue. Ready.`

5. **Commit all changes** from the pass in a single commit:
   `chore: session-start self-improvement pass — YYYY-MM-DD`

Then wait for the user's first message.

## Layer awareness

- **This repo is Layer 2** (a skill product). It is not the framework (Layer 1). Do not commit framework-level changes here.
- The framework lives at `C:\Users\user\Documents\Skills\skill-atelier\`.
- Changes to framework files commit there. Changes to Memex files commit here. Never mix.

## Working rules

1. **Research before design.** No format or schema is locked until sources are ingested and synthesized. See `sources/` for ingestion workflow.
2. **Source everything significant.** When research material informs a decision, it should be in `sources/analyzed/` before the decision is logged.
3. **Capture lessons after meaningful work.** After non-trivial sessions, capture to `lessons/inbox/`.
4. **Propose wiki entries during sessions; approve at session close.** Do not unilaterally edit `.ai/wiki/` mid-flow. Exception: the session-start queue-processing pass (see ## Session start) may write wiki drafts and promote lessons autonomously — this is the only context where gates are bypassed.
5. **Releases are deliberate.** Do not auto-promote to `dist/`. The release skill (from Skill Atelier's `meta/cut-release/`) is the only path.
6. **Surface conflicts with goals.** If a request conflicts with `GOALS.md`, flag before acting.

## When in doubt

Read `GOALS.md`. Check alignment. If still uncertain, surface it to the user.
