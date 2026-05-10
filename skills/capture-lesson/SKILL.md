---
description: "Use when the user wants to capture a lesson from the current session — either on demand (\"capture this as a lesson\", \"I noticed X\") or at session end to review and propose lessons from the conversation. Also use when the user invokes /capture-lesson. Do NOT use for writing wiki pages (use capture) or reviewing and promoting lessons (use review-lessons)."
---

# capture-lesson — write a lesson file

## Mode detection

- **On-demand** — user provides a topic, observation, or points to something from the conversation. Handle first.
- **Session-end** — user invokes with no specific topic ("what lessons should we capture?", `/capture-lesson` with no args).

Both modes share the approval gate. Commit behavior differs by mode.

**After detecting mode**, confirm the target project root:

- **Zero detectable projects** (no `lessons/inbox/` at any accessible root): stop. Tell the user: 'No lessons directory found. Create `lessons/inbox/` and `lessons/feedback/` in your project root before running capture-lesson.' Do not create directories automatically. Do not proceed.
- **Exactly one detectable project**: proceed. Announce: 'Writing to `<path>/lessons/`.' No confirmation needed.
- **More than one detectable project**: ask the user which project. Wait for explicit choice.

A project is detectable if it contains `lessons/inbox/` at its root — check each root at this fixed path only. Do not recurse.

---

## On-demand mode

1. **Extract content** from user input / conversation:
   - `id`: `<project>:lesson:<slug>` — prompt if uncertain; never guess
   - `title`, `slug` (include only if it differs from the filename stem; omit otherwise), `tags`, `stream` (auto-routed — see REFERENCE.md), `status` (always `draft` on NEW or REPAIR)
   - Body: Observation / Why it matters / How to apply

2. **Check for existing file** at `lessons/<stream>/<slug>.md`:
   - Not found → prepare NEW
   - Found → read it; prepare diff summary (one line per changed field; body changes as `body: content updated`)
   - Found but malformed (unparseable YAML or required field absent) → REPAIR: re-derive all fields as if NEW; gate shows `[REPAIR: previous write failed — re-drafted from conversation]`

3. **Show approval gate:**
   ```
   Will write: lessons/<stream>/<slug>.md
   Title: <title>
   Stream: <stream>  |  Tags: [...]
   ~<N> lines
   [NEW]  or  [UPDATE: <summary>]  or  [REPAIR: previous write failed — re-drafted from conversation]
   Approve? (yes / edit / skip / cancel)
   ```
   - **yes** → step 4
   - **edit** → apply correction, re-show gate
   - **skip** / **cancel** / **abort** → stop, write nothing
   - Any other message → treat as edit instruction

4. **On approval** → write file (field rules in REFERENCE.md), stage it, commit: `lessons: capture — <title>`

---

## Session-end mode

1. **Sweep** the conversation for lesson candidates:
   - Non-obvious observations, mid-session corrections, decisions with a "why", patterns that would help a future AI avoid a mistake
   - Skip: task-local notes, anything obvious from code or git history, ephemeral state

2. **Show candidate list** before any gates:
   ```
   Found N lesson candidates:
   1. <title> (inbox)
   2. <title> (feedback)
   Proceed through each? (yes / skip N / cancel)
   ```
   - **yes** → gate each in order
   - **skip N** → exclude candidate N, gate the rest
   - **cancel** → stop, write nothing
   - No candidates found → report "No lesson candidates found in this session." Done.

3. **Gate each candidate** one at a time — same approval gate as on-demand.

4. **After all gates** → stage all approved lessons; one commit: `lessons: capture — N lessons`

---

## Error handling

See REFERENCE.md error table and commit message format.
