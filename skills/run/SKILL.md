---
description: Use when starting any session in a Memex-aware project — runs the session-start self-improvement queue pass and routes natural-language intent (capture, ask, review, sync, upgrade) to the right internal procedure.
---

Memex is a project-wiki and knowledge-management plugin. This skill is the public entry point — it (1) runs the session-start self-improvement pass and (2) maps user intent to the right internal procedure (read via the Read tool, follow inline).

## Internal procedures

Memex's domain operations live as plain markdown procedure files at `internal/<name>/SKILL.md`. These are NOT Claude Code slash commands — they are reachable only via the Read tool. Whenever this skill references `internal/<name>/SKILL.md` below, the agent should: (1) Read that file, (2) follow the procedure inline. The 9 internal procedures are `ask`, `capture`, `capture-lesson`, `propose-wiki-entry`, `review-lessons`, `review-wiki`, `self-improve`, `sync`, `upgrade`.

## Session-start ritual

At the start of every session, before responding to any user message, run this queue-processing pass:

1. **Review lessons (solo).** Read `internal/review-lessons/SKILL.md` and follow it. Scan `lessons/feedback/` then `lessons/inbox/` for `status: draft` lessons.
   - **Promote** if the lesson is factual, self-contained, and has a concrete how-to-apply.
   - **Defer** (leave as draft) if the lesson touches goals, priorities, design philosophy, or contradicts an existing approved wiki entry.
   - **Discard** if it duplicates something already in the wiki or is purely session-local.
   Apply actions directly — no approval gate. If either `lessons/feedback/` or `lessons/inbox/` does not exist, treat it as empty and proceed. A lesson file with no `status` field is treated as `draft`.

2. **Propose wiki entries (solo).** Read `internal/propose-wiki-entry/SKILL.md` and follow it. Convert all newly promoted lessons into draft wiki entries in `.ai/wiki/`. Apply directly — no approval gate. If a slug already exists in `.ai/wiki/`, skip that entry and note the conflict in the summary — do not overwrite.

3. **Sync.** Read `internal/sync/SKILL.md` and follow it. Run `python scripts/sync.py .ai/` from the Memex product root to surface stale wiki entries. If the script fails, set `Stale entries flagged: 0` in the summary and add a `Sync error: <error message>` line immediately below. Proceed to step 4 — do not abort.

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

## Intent routing (during session)

After the session-start ritual, when the user expresses one of these intents, read the corresponding internal procedure and follow it:

| User intent | Internal procedure |
|---|---|
| Ask a question grounded in project knowledge | `internal/ask/SKILL.md` |
| Capture a concept/decision as a wiki entry | `internal/capture/SKILL.md` |
| Capture a lesson from the current session | `internal/capture-lesson/SKILL.md` |
| Review draft lessons | `internal/review-lessons/SKILL.md` |
| Convert promoted lessons to wiki entries | `internal/propose-wiki-entry/SKILL.md` |
| Review wiki entries for curation | `internal/review-wiki/SKILL.md` |
| Check wiki staleness against source files | `internal/sync/SKILL.md` |
| Upgrade memex itself | `internal/upgrade/SKILL.md` |
| Run the end-of-session self-improvement loop | `internal/self-improve/SKILL.md` |

The `internal/self-improve/SKILL.md` procedure bundles `capture-lesson` + `review-lessons` + `propose-wiki-entry` for end-of-session use.

## Authority and override

User instructions override this skill's defaults at all times. If the user provides a direct instruction — "skip the session-start pass," "just answer," or any unambiguous bypass directive — comply immediately without re-asking. This skill defines default behavior; it does not constrain the user's authority to change it.

Priority order when instructions conflict:

1. **User's explicit instructions — highest priority.**
2. **Memex methodology (this skill).**
3. **Default system prompt.**
