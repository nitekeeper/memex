---
description: "Use when the user wants to capture a concept, decision, or summary as a project-wiki page — either on demand during a session (\"capture this as a wiki entry\") or at session end to review and propose pages from the conversation. Also use when the user invokes /capture. Do NOT use for ingesting external sources (use meta:ingest-source) or for staleness checking (use sync)."
---

# capture — write a project-wiki page

## Mode detection

- **On-demand** — user provides a topic, title, draft, or points to a decision from the conversation. Handle this first.
- **Session-end** — user invokes at end of session with no specific topic ("what should we capture?", `/capture` with no args).

Both modes share the approval gate. Commit behavior differs by mode.

**After detecting the mode and before executing any mode steps**, confirm the target project root: identify which project's `.ai/wiki/` is the target. In a multi-project workspace, state it explicitly: "Writing to `<path>/.ai/wiki/`." If more than one project is detectable in the current workspace, always ask before proceeding — do not infer the target from recency, activity, or conversational context alone.

---

## On-demand mode

1. **Extract content** from user input and/or conversation context:
   - `id`: `<project>:<type>:<slug>` — prompt if uncertain; never guess
   - `title`, `slug`, `tags`, `status` (always `draft` on first write)
   - `describes-files` (only if this page tracks specific source files)
   - `body`: synthesized from conversation or polished from user draft

2. **Check for existing page** at `.ai/wiki/<slug>.md`:
   - Not found → prepare creation plan
   - Found → read it; prepare diff description (which fields and body sections change). Format the diff as one line per changed item: list each changed field by name; describe body changes as `body: <section name> updated`. Example: `[UPDATE: title changed, body: rationale section added]`. Do not include full before/after diffs in the gate.

3. **Show approval gate** before touching any file:
   ```
   Will write: .ai/wiki/<slug>.md
   Title: <title>
   Status: <status>  |  Tags: [...]
   ~<N> lines
   [NEW] or [UPDATE: <summary of changes>]
   Approve? (yes / edit / skip)
   ```
   If user says **edit**: apply the correction to the current draft, return to step 3 to show the updated gate. If the user says `cancel`, `abort`, or `quit` at any point in the edit loop, treat as skip — stop; do not write anything.
   If user says **skip**: stop; do not write anything.
   Any other message: treat as an edit instruction, apply the correction to the current draft, return to step 3 with the updated gate.

4. **On approval**, write the file:
   - `created`: today if NEW; preserve existing value if UPDATE. `updated`: today (YYYY-MM-DD) — but only if content changed. If the UPDATE diff from step 2 was empty (no fields and no body content changed), do not write the file; tell the user "No changes detected — file not updated." and stop.
   - `synced-at-commit`: do not set — the sync skill manages this field
   - Conform to `docs/WIKI_PAGE_FORMAT.md`. See `REFERENCE.md` for field details.

5. **Validate**: run `python scripts/rebuild.py .ai/`
   - On error: show it, stop, do not commit. Leave file in place for inspection. Note: the file left in place may be malformed. On retry, step 2 will detect it — treat it as a draft under repair, not a valid existing page, and re-draft the body from the current conversation rather than diffing against the malformed content.

6. **Auto-commit**: `wiki: capture <slug> — <title>`

---

## Session-end mode

1. **Review conversation.** Find: decisions made, patterns named, constraints locked, concepts defined. Skip any concept for which a file already exists at `.ai/wiki/<slug>.md`, or which was explicitly captured earlier in the current session. Skip anything too ephemeral for the next session. If no candidates remain after filtering, tell the user: "No new wiki pages identified from this session." Stop.

2. **Propose a batch list** before touching any file:
   ```
   Found N candidates:
   1. .ai/wiki/<slug>.md — "<title>" [NEW]
   2. .ai/wiki/<slug>.md — "<title>" [UPDATE: <summary>]
   Approve all / approve individually / skip?
   ```
   If user says **skip**: stop; do not write anything.
   If the user names specific pages to skip (e.g. "skip 2 and 4"): switch to approve individually, treating the named pages as skipped.

3. **Approve all**: run steps 1–5 of on-demand mode for each page (using content extracted in step 1, not fresh user input; do not execute on-demand step 6 — the batch commit in step 6 below replaces it). **Intervenes** means the user sends any message during processing that is not a silent pass — a question, correction, "wait", "stop", "change X", or any message other than no response. On intervention, pause immediately and switch to approve individually for that page and all remaining pages. Present the approval gate (on-demand step 3) for the current in-progress page using the draft already computed — do not write it yet. Session-end step 6 (single batch commit) still applies at the end of the run.

4. **Approve individually**: run steps 1–5 of on-demand mode for each page (do not execute on-demand step 6 — the batch commit in step 6 below replaces it); user approves or skips per page.

5. **Mid-batch validation failure**: if `rebuild.py` fails on any page during a batch run, stop immediately. Do not commit anything. List every file written so far in the batch as relative paths from the project root, one per line, so the user can inspect or delete them. Do not proceed until the user explicitly resolves the failure. Then re-enter at step 2 with only the pages not yet written. Do not re-propose pages already on disk from this batch. For any already-written page the user explicitly wants to re-process, show `[ALREADY WRITTEN — overwrite?]` in the approval gate instead of `[UPDATE]`.

6. **One commit** for the batch (only when all approved-and-written pages pass validation): `wiki: capture session — <N> pages`

---

## Error handling

| Situation | Action |
|---|---|
| `rebuild.py` errors in on-demand mode | Show error, stop, do not commit. Leave file in place for inspection. |
| `rebuild.py` errors in session-end mode | See step 5 above — stop, list all written files as relative paths, re-enter at step 2. |
| `id` already exists at a different path | Flag before writing. Ask the user: (a) assign a new id to the new page, (b) update the existing page at its current path, or (c) cancel. Do not proceed until one option is explicitly chosen. |
| Required field missing | Prompt user; never guess `id`. |

For field definitions and id conventions, see `REFERENCE.md`.
