# capture-lesson skill — design spec
_2026-05-10_

## Scope

One skill in the Memex self-improvement loop: `capture-lesson`. Writes lesson files from session observations into the project's `lessons/` directory. Companion to `review-lessons` (not yet built).

---

## Architecture

Three deliverables:

| File | Purpose |
|---|---|
| `skills/capture-lesson/SKILL.md` | Skill procedure: mode detection, on-demand flow, session-end flow, approval gate, commit behavior |
| `skills/capture-lesson/REFERENCE.md` | Lesson format spec, stream routing rules, commit message format, error table |
| `docs/LESSON_FORMAT.md` | Standalone format document — readable outside the skill |

No script. Pure LLM skill, mirroring the `capture` skill's structure.

**Project detection:** looks for `lessons/inbox/` at the project root (fixed-path check, same logic as `capture` uses for `.ai/wiki/`).

- Zero detectable projects → stop with instructions
- Exactly one → proceed, announce target
- More than one → ask user to choose; wait for explicit selection

---

## Lesson format

```
---
id: <project>:lesson:<slug>
title: <title>
stream: inbox | feedback
status: draft | promoted | discarded
tags: [...]
created: YYYY-MM-DD
---

<body>
```

**Body structure** (2–3 short paragraphs max):

- **Observation** — what happened or was noticed
- **Why it matters** — the non-obvious implication; what would go wrong without this lesson
- **How to apply** — concrete guidance for next time

`feedback` stream lessons follow the same structure, but the Observation is the user's stated direction verbatim (or close to it), not an AI inference.

**Filename:** `lessons/<stream>/<slug>.md` — slug derived from title, kebab-case.

---

## Stream routing

| Origin | Stream |
|---|---|
| AI proposes the lesson unprompted | `inbox/` |
| User explicitly states feedback, a correction, or direction | `feedback/` |
| Ambiguous | `inbox/` (default) |

---

## Mode detection

- **On-demand** — user provides a topic or points to something from the conversation ("capture this as a lesson", "I noticed X"). Handle first.
- **Session-end** — user invokes with no specific topic ("what lessons should we capture?", `/capture-lesson` with no args).

Both modes share the approval gate. Commit behavior differs.

---

## On-demand mode

1. **Extract content** from user input / conversation: `id`, `title`, `slug`, `tags`, `stream` (auto-routed), body
2. **Check for existing file** at `lessons/<stream>/<slug>.md`:
   - Not found → prepare NEW
   - Found → read it; prepare diff summary (one line per changed field; body changes as `body: content updated`)
   - Found but malformed → REPAIR path: re-derive all fields as NEW; scan raw text for `synced-at-commit:` line and preserve if present
3. **Show approval gate:**
   ```
   Will write: lessons/inbox/<slug>.md
   Title: <title>
   Stream: inbox | feedback  |  Tags: [...]
   ~<N> lines
   [NEW]  or  [UPDATE: <summary>]  or  [REPAIR: previous write failed — re-drafted from conversation]
   Approve? (yes / edit / skip / cancel)
   ```
   - **yes** → step 4
   - **edit** → apply correction, re-show gate
   - **skip** / **cancel** / **abort** → stop, write nothing
   - Any other message → treat as edit instruction
4. **On approval** → write file, stage it, commit: `lessons: capture — <title>`

---

## Session-end mode

1. **Sweep** the conversation for lesson candidates — look for: non-obvious observations, mid-session corrections, decisions with a "why" worth preserving, patterns that would help a future AI avoid a mistake
2. **Filter** — skip task-local notes, anything obvious from code or git history, ephemeral state
3. **Show candidate list** before any gates:
   ```
   Found N lesson candidates:
   1. <title> (inbox)
   2. <title> (feedback)
   3. <title> (inbox)
   Proceed through each? (yes / skip N / cancel)
   ```
   - **yes** → gate each in order
   - **skip N** → exclude candidate N, gate the rest
   - **cancel** → stop, write nothing
4. **Gate each candidate** one at a time — same approval gate as on-demand
5. **After all gates** → stage all approved lessons; one commit: `lessons: capture — N lessons`

If sweep finds no candidates: report "No lesson candidates found in this session." Done.

---

## Error handling

| Situation | Action |
|---|---|
| No `lessons/inbox/` found at project root | Stop: "No lessons directory found. Create `lessons/inbox/` and `lessons/feedback/` in your project root before running capture-lesson." |
| Multiple detectable projects | Ask user which project to target. Wait for explicit choice. |
| Existing file malformed | REPAIR path: re-derive all fields as NEW. Gate shows `[REPAIR: previous write failed — re-drafted from conversation]`. |
| `git commit` fails | Show error, do not retry. Written files remain on disk uncommitted. |
| Session-end sweep finds no candidates | Report "No lesson candidates found in this session." Done. |

---

## Testing

`tests/test_capture_lesson_skill.py` — scenario-based tests:

1. On-demand: NEW lesson written to `inbox/` with correct frontmatter
2. On-demand: NEW lesson written to `feedback/` when user-direct
3. On-demand: UPDATE detected correctly when file exists
4. On-demand: REPAIR path when existing file is malformed
5. Session-end: candidate list shown before gates
6. Session-end: skipped candidates not written
7. Session-end: single commit covers all approved lessons
8. Session-end: no candidates found → stops cleanly
9. No `lessons/` directory → stops with correct message
