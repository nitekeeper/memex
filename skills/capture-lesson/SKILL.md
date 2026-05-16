---
description: "Use when the user wants to capture a lesson from the current session — either on demand (\"capture this as a lesson\", \"I noticed X\") or at session end to review and propose lessons from the conversation. Do NOT use for writing wiki pages (use capture), reviewing or promoting lessons (use review-lessons), ingesting external sources (use meta:ingest-source), or checking staleness (use sync)."
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
   Approve? (yes / edit / skip / cancel / quit)
   ```
   - **yes** → step 4
   - **edit** → apply correction, re-show gate
   - **skip** / **cancel** / **abort** / **quit** → stop, write nothing
   - Any other message → treat as edit instruction

4. **On approval** → write file:
   - `created`: today if NEW or REPAIR; preserve existing value on UPDATE
   - `status`: always `draft` on NEW or REPAIR; preserve on UPDATE
   - No `updated` field — lessons do not track update history
   Stage the file. Commit (apply em dash encoding check from REFERENCE.md): `lessons: capture — <title>`

---

## Session-end mode

1. **Sweep** the conversation for lesson candidates:
   - Non-obvious observations, mid-session corrections, decisions with a "why", patterns that would help a future AI avoid a mistake
   - Skip: task-local notes, anything obvious from code or git history, ephemeral state, any lesson already written during this session, any lesson whose file already exists at `lessons/<stream>/<slug>.md`

2. **Show candidate list** before any gates:
   ```
   Found N lesson candidates:
   1. <title> (inbox)
   2. <title> (feedback)
   Proceed through each? (yes / cancel)
   (To skip a specific candidate, say "skip" at that candidate's approval gate.)
   ```
   - **yes** → gate each in order
   - **cancel** → stop, write nothing
   - No candidates found → report "No lesson candidates found in this session." Done.

3. **Gate each candidate** one at a time — same approval gate as on-demand. `cancel`, `abort`, or `quit` at any inner gate stops the entire batch; already-approved files remain written on disk and will be included in the step 4 commit. Use `yes` to approve; any other message is treated as an edit instruction (do not use casual affirmations like "looks good" as they trigger an edit loop).

4. **After all gates** → stage all approved lessons. Commit (apply em dash encoding check from REFERENCE.md): `lessons: capture — N lessons`

---

## Error handling

See REFERENCE.md error table and commit message format.
