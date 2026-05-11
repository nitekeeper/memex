---
description: "Use when the user wants to review draft lessons — either on demand (\"review my lessons\", \"let's go through the inbox\") or at session close as part of the self-improvement loop. Do NOT use for writing new lessons (use capture-lesson), writing wiki entries (use capture), checking wiki staleness (use sync), or searching knowledge (use ask)."
---

# review-lessons — review and action draft lessons

## Mode detection

- **On-demand** — user explicitly asks to review lessons. Handle first.
- **Session-close** — user invokes at session end ("let's close out", `/review-lessons` with no args). Same procedure.

**After detecting mode**, confirm the target project root:

- **Zero detectable projects** (no `lessons/inbox/` at any accessible root): stop. Tell the user: 'No lessons directory found. Create `lessons/inbox/`, `lessons/feedback/`, and `lessons/promoted/` in your project root before running review-lessons.' Do not create directories. Do not proceed.
- **Exactly one detectable project**: proceed. Announce: 'Reviewing lessons in `<path>/lessons/`.' No confirmation needed.
- **More than one detectable project**: ask the user which project. Wait for explicit choice.

A project is detectable if it contains `lessons/inbox/` at its root — check each root at this fixed path only. Do not recurse.

---

## Procedure

1. **Scan** for draft lessons:
   - Read all `.md` files in `lessons/feedback/` and `lessons/inbox/` with `status: draft`
   - Skip files with `status` not `draft`
   - Bucket into two groups:
     - **Held**: files with `held-for-review: true` (feedback stream first, then inbox)
     - **Regular**: all other draft files (feedback stream first, then inbox)
   - Review order: held items first, then regular drafts

2. **Show candidate list** before any action:
   ```
   Found N draft lessons (H held, F feedback, I inbox):
   1. <title> (feedback) [HELD: philosophy]
   2. <title> (inbox) [HELD: contradiction]
   3. <title> (feedback)
   4. <title> (inbox)
   Proceed? (yes / cancel)
   ```
   (Show `[HELD: <reason>]` only for held items. Omit `H held` from the header count when H is 0.)
   - **yes** → review each in order
   - **cancel** → stop, change nothing
   - No draft lessons found → report "No draft lessons to review." Done.

3. **For each lesson**, show a summary block and offer three choices:

   ```
   --- Lesson <n> of N ---
   Title: <title>
   Stream: <stream>  |  Tags: [...]
   
   How to apply: <how-to-apply content>
   
   Action? (promote / discard / defer)
   ```
   For held items, prepend the held marker and add a reason line:
   ```
   --- Lesson <n> of N --- [HELD: <reason>]
   Title: <title>
   Stream: <stream>  |  Tags: [...]

   Held reason: contradiction | touches philosophy/goals | low confidence
   How to apply: <how-to-apply content>

   Action? (promote / discard / defer)
   ```
   When a held lesson is promoted, also clear `held-for-review` and `held-reason` from its frontmatter.

   - **promote** → see Promote action
   - **discard** → ask "Log a reason? (enter reason, or press enter to just delete)"
     - Reason provided → Discard-with-reason action
     - No reason → Delete action
   - **defer** → no change; continue to next lesson
   - Any other message → treat as a clarifying question; re-show block after answering

4. **After all lessons** → commit if any files were changed (see REFERENCE.md commit format). If only deletions occurred, use `git rm` to stage them.

---

## Actions

### Promote

1. Update `status: promoted` in the file's frontmatter.
2. Move the file to `lessons/promoted/<slug>.md` (preserve filename).
3. Stage the move: `git rm lessons/<stream>/<slug>.md` + `git add lessons/promoted/<slug>.md`.
4. Show the lesson's **How to apply** section and suggest a follow-up:
   - If lesson feels like a wiki entry: "Consider running `capture` to create a wiki entry."
   - If lesson points to a skill update: "Consider updating the relevant skill."
   - If unsure: "Consider whether this warrants a wiki entry or skill update."
   The follow-up is informational only — do not take further action automatically.

### Discard-with-reason

1. Update `status: discarded` in the file's frontmatter.
2. Add `discard-reason: <reason>` field to frontmatter.
3. Leave the file in its current location (do not move).
4. Stage the change: `git add lessons/<stream>/<slug>.md`.

### Delete (discard, no reason)

1. Delete the file from disk.
2. Stage: `git rm lessons/<stream>/<slug>.md`.

---

## Error handling

See REFERENCE.md error table and commit message format.
