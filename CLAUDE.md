# CLAUDE.md — entering Memex

You are operating inside the **Memex product repo**. Memex is Product 1 of Skill Atelier. This repo holds the research, design, skill source, and releases for the Memex product.

## Read at session start

1. `GOALS.md` — north-star, current focus, anti-goals.
2. `ROADMAP.md` — what's in flight and what's next.
3. `DESIGN_NOTES.md` — decisions made so far.

## Session start

At the start of every session, before responding to any user message, run the self-improvement queue-processing pass:

1. **`review-lessons` (solo)** — scan `lessons/feedback/` then `lessons/inbox/` for `status: draft` lessons.
   - **Promote** if the lesson is factual, self-contained, and has a concrete how-to-apply.
   - **Defer** (leave as draft) if the lesson touches goals, priorities, design philosophy, or contradicts an existing approved wiki entry.
   - **Discard** if it duplicates something already in the wiki or is purely session-local.
   - Apply actions directly — no approval gate.
   If either `lessons/feedback/` or `lessons/inbox/` does not exist, treat it as empty and proceed to the next step.
   Treat a lesson file with no `status` field as `draft`.

2. **`propose-wiki-entry` (solo)** — convert all newly promoted lessons into draft wiki entries in `.ai/wiki/`. Apply directly — no approval gate.
   If a slug already exists in `.ai/wiki/`, skip that entry and note the conflict in the summary — do not overwrite.

3. **`sync`** — run `python scripts/sync.py .ai/` from the Memex product root (`C:\Users\user\Documents\Skills\memex`) to surface stale wiki entries. If the script fails, set `Stale entries flagged: 0` in the summary and add a `Sync error: <error message>` line immediately below it. Proceed to Step 4 — do not abort the pass.

4. **Show summary** using this exact format:

   ```
   Session-start self-improvement pass — YYYY-MM-DD
     Lessons reviewed: N
       Promoted: X
       Deferred (needs collaborative review): Y
       Discarded: Z
     Wiki entries proposed: M
     Wiki entry conflicts skipped: C
       - <slug> (already exists)
     Stale entries flagged: K
       - <title> (.ai/wiki/<slug>.md)
     Sync error: <error message>    ← sibling field, not a sub-item; only shown when sync fails; omit when sync succeeds
   ```

   If `K` is 0, show `Stale entries flagged: 0` and omit the bullet list.
   If `C` is 0, show `Wiki entry conflicts skipped: 0` and omit the bullet list.
   If both lesson directories were empty (or absent) and no lessons were promoted, show: `Session-start self-improvement pass — nothing in queue. Ready.`

5. **Commit all changes** from the pass in a single commit: `chore: session-start self-improvement pass — YYYY-MM-DD` (substitute today's date). If the pass produced no file changes, skip the commit and note "no changes committed" in the summary.

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
