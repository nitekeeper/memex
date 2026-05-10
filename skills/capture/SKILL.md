---
description: "Use when the user wants to capture a concept, decision, or summary as a project-wiki page — either on demand during a session (\"capture this as a wiki entry\") or at session end to review and propose pages from the conversation. Also use when the user invokes /capture. Do NOT use for ingesting external sources (use meta:ingest-source) or for staleness checking (use sync)."
---

# capture — write a project-wiki page

## Mode detection

- **On-demand** — user provides a topic, title, draft, or points to a decision from the conversation. Handle this first.
- **Session-end** — user invokes at end of session with no specific topic ("what should we capture?", `/capture` with no args).

Both modes share the approval gate. Commit behavior differs by mode.

**After detecting the mode and before executing any mode steps**, confirm the target project root:

- **Zero detectable projects** (no `.ai/wiki/` subdirectory found in any directory accessible from the current workspace): stop immediately. Tell the user: 'No project wiki found. Create an `.ai/wiki/` directory in your target project root before running capture.' Do not proceed.
- **Exactly one detectable project**: proceed automatically. State the target before the first step: 'Writing to `<absolute-path-to-project>/.ai/wiki/`.' No user confirmation required.
- **More than one detectable project**: ask the user which project to target. Do not infer from recency, activity, or conversational context. Wait for an explicit choice.

A project is detectable if it has an `.ai/wiki/` subdirectory reachable from the current working directory or any open workspace root.

Once a project is confirmed, hold that project's `.ai/wiki/` directory as the target for every `.ai/wiki/` path reference throughout this run. All step references to `.ai/wiki/<slug>.md` mean `<that-project>/.ai/wiki/<slug>.md`.

---

## On-demand mode

1. **Extract content** from user input and/or conversation context:
   - `id`: `<project>:<type>:<slug>` — prompt if uncertain; never guess
   - `title`, `slug` (include only if it would differ from the filename stem; omit otherwise), `tags`, `status` (always `draft` on first write)
   - `describes-files` (only if this page tracks specific source files)
   - `body`: synthesized from conversation or polished from user draft

2. **Check for existing page** at `.ai/wiki/<slug>.md`:
   - Not found → prepare creation plan
   - Found and valid → read it; prepare diff description (which fields and body sections change). Format the diff as one line per changed item: list each changed field by name; describe body changes as `body: <section name> updated` — if the body has no named sections, write `body: content updated`. Example: `[UPDATE: title changed, body: rationale section added]`. Do not show full before/after diffs in the gate display (the agent may compute a full diff internally to support the edit/correction path).
   - Found but malformed (caused a `rebuild.py` validation error in a previous attempt) → do not diff against the malformed content. Re-draft the body from the current conversation. Show gate as `[REPAIR: previous write failed — re-drafted from conversation]`. This path is exempt from the empty-diff guard in step 4.

3. **Show approval gate** before touching any file:
   ```
   Will write: .ai/wiki/<slug>.md
   Title: <title>
   Status: <status>  |  Tags: [...]
   ~<N> lines
   [NEW]  or  [UPDATE: <summary of changes>]  or  [REPAIR: previous write failed — re-drafted from conversation]
   Approve? (yes / edit / skip / cancel)
   ```
   Evaluate responses in this order:
   If user says **yes**: proceed to step 4.
   If user says **cancel**, **abort**, or **quit**: treat as skip — stop; do not write anything.
   If user says **edit**: apply the stated correction to the current draft, return to step 3 to show the updated gate.
   If user says **skip**: stop; do not write anything.
   Any other message: treat as an edit instruction — interpret the full message as the correction, apply it to the current draft, return to step 3 with the updated gate. (In session-end approve-all mode, this branch does not apply — session-end step 3's approve-all intervention logic takes precedence. In session-end approve-individually mode, unexpected messages are handled by session-end step 4's intervention note.)

4. **On approval**, write the file:
   - `created`: today if NEW; preserve existing value if UPDATE.
   - `updated`: today (YYYY-MM-DD) if content changed; preserve existing value if nothing changed. For this check, exclude the `updated` field itself from the diff comparison. This guard applies only on the UPDATE path — on the NEW path, always proceed to write regardless of diff state. If the UPDATE diff from step 2 is empty after excluding `updated` (no other fields and no body content changed), do not write the file; tell the user "No changes detected — file not updated." and stop. **Exception: if step 2 flagged this page as a REPAIR path, always proceed to write regardless of diff state.**
   - `status`: preserve existing value on UPDATE — do not reset to `draft`.
   - If the existing page has `status: approved`, add a warning line to the approval gate display before the user confirms: `[WARNING: this page is currently approved — content will be updated but status preserved]`. Do not demote status automatically.
   - `synced-at-commit`: do not set — the sync skill manages this field
   - Conform to `docs/WIKI_PAGE_FORMAT.md` in the confirmed project root. See `REFERENCE.md` for field details.

5. **Validate**: run `python scripts/rebuild.py .ai/`
   - On error: show it, stop, do not commit. Leave file in place for inspection. Note: a file left on disk after a `rebuild.py` failure is considered malformed. On retry, step 2 will find it — the 'Found but malformed' branch applies: re-draft from conversation, show `[REPAIR]` gate, and proceed normally. This path bypasses the empty-diff guard.

6. **Auto-commit**: `wiki: capture <slug> — <title>`

---

## Session-end mode

1. **Review conversation.** Find: decisions made, patterns named, constraints locked, concepts defined. Skip any concept for which a file already exists at `.ai/wiki/<slug>.md` (derive the candidate slug using the same rules as on-demand step 1 before checking), or which was explicitly captured (NEW or UPDATE) earlier in the same conversation. This skip is intentional: new content arising after an earlier capture in the same session is not re-proposed; the user may invoke on-demand mode separately for any update. Skip anything too ephemeral for the next session. If no candidates remain after filtering, tell the user: "No new wiki pages identified from this session." Stop.

2. **Propose a batch list** before touching any file:
   ```
   Found N candidates:
   1. .ai/wiki/<slug>.md — "<title>" [NEW]
   2. .ai/wiki/<slug>.md — "<title>" [UPDATE: <summary>]
   Approve all / approve individually / skip?
   ```
   If user says **approve all**: proceed to step 3.
   If user says **approve individually**: proceed to step 4.
   If user says **skip**: stop; do not write anything.
   If the user names specific pages to skip (e.g. "skip 2 and 4"): switch to approve individually, treating the named pages as skipped.
   Any other message: treat as an edit instruction for the candidate list — apply corrections to affected candidates (titles, slugs, removals), then re-display the updated batch list and wait for an approval response.

3. **Approve all**: run steps 1–5 of on-demand mode for each page (using content extracted in step 1, not fresh user input; do not execute on-demand step 6 — the batch commit in step 6 below replaces it; if the `id` for any page is uncertain during batch execution, derive it from the slug rather than pausing to prompt — flag the derived id in the approval gate so the user can correct it). **Intervenes** means a message received while the agent is executing on-demand steps 1, 2, 4, or 5 for the current page — not while the approval gate (on-demand step 3) is actively awaiting a response (gate responses are handled by on-demand step 3's own branches). On intervention, pause immediately. Check whether the file for the in-progress page exists on disk:
   - If the file does **not yet exist on disk** for this page: present the approval gate (on-demand step 3) using the draft already computed — do not write yet. (In session-end approve-all mode, on-demand step 3's 'any other message → edit' branch does not apply — use this intervention gate only for yes/edit/skip/cancel.)
   - If the file **already exists on disk** for this page (written in this run): present the approval gate showing `[ALREADY WRITTEN — review?]` (written this run — approving re-runs validation only; skipping leaves the file on disk as-is); if the user approves, run on-demand step 5 (validate) and continue; if the user skips, validate the file immediately (run on-demand step 5) before continuing — do not leave an unvalidated file on disk.
   After handling the current page, continue with session-end step 4 (approve individually) for all remaining pages. Session-end step 6 (single batch commit) still applies at the end of the run.

4. **Approve individually**: run steps 1–5 of on-demand mode for each page (do not execute on-demand step 6 — the batch commit in step 6 below replaces it; if the `id` for any page is uncertain during batch execution, derive it from the slug rather than pausing to prompt — flag the derived id in the approval gate so the user can correct it); user approves or skips per page. If the user sends any message that is not yes, edit, skip, cancel, abort, or quit during the approval gate for a page, treat it as an edit instruction for that page's draft — apply the correction and re-show the approval gate for that page.

5. **Mid-batch validation failure**: if `rebuild.py` fails on any page during a batch run, stop immediately. Do not commit anything. List every file written so far in this batch run as relative paths from the project root, one per line. Retain this list as your written-pages record for the remainder of this run. Resolution means one of: (a) the user fixes the underlying issue and confirms — re-run `rebuild.py` to verify before proceeding; (b) the user instructs you to skip or delete the failing page — remove it from the candidate set; (c) the user abandons the batch — stop entirely; files written before the halt remain on disk uncommitted and the user handles them manually. Do not accept silence or an unrelated message as resolution. The written-pages record persists across re-entries — do not discard it on re-entry; continue appending to it if further failures occur. Then re-enter at session-end step 2 with only the pages from this batch not yet written to disk (i.e., pages not in your written-pages record); update N to reflect the reduced candidate set — do not carry forward the original N. Do not re-propose pages in your written-pages record. If the user explicitly names an already-written page for re-processing, show `[ALREADY WRITTEN — overwrite?]` (user explicitly requested re-processing — approving re-writes the file then validates; skipping leaves the file on disk as-is) in the approval gate instead of `[UPDATE]`; if the user approves, proceed to on-demand steps 4 and 5 (write and validate), then continue the batch.

6. **One commit** for the batch (only when all approved-and-written pages pass validation): `wiki: capture session — <N> pages` where N is the count of pages successfully written and validated across all phases of this run, including pages written before any step-5 failure and pages written after re-entry. 'This run' spans the full session from initial batch proposal through all re-entries triggered by step 5.

---

## Error handling

| Situation | Action |
|---|---|
| `rebuild.py` errors in on-demand mode | Show error, stop, do not commit. Leave file in place for inspection. Tell the user: 'The file has been left on disk for inspection. Fix the issue, then re-invoke the capture skill for the same topic — step 2 will detect the malformed file automatically and apply the REPAIR path.' On re-invocation, no special user action is required beyond invoking capture again. |
| `rebuild.py` errors in session-end mode | See step 5 above — stop, list all written files as relative paths, re-enter at step 2. |
| `id` already exists at a different path | Flag before writing. Ask the user: (a) assign a new id to the new page — prompt the user for the new `id` only, apply it to the current draft, then re-enter at on-demand step 2 to check for an existing page at the new slug, then continue; (b) update the existing page at its current path — re-enter at on-demand step 2 using the existing page's path, treating the current draft as the proposed update; proceed through steps 2–6 normally so the diff gate is shown; (note: step 4 will preserve the existing page's `status` — if the existing page is `approved`, the update will remain `approved`); (c) cancel — stop; do not write anything. Do not proceed until one option is explicitly chosen. |
| Required field missing | Prompt the user for the missing field. If the user provides a value, apply it and re-enter at on-demand step 1 to continue extraction. If the user cannot provide the value or declines, stop — do not write anything. Never guess `id`. |
| No detectable project (no `.ai/wiki/` directory found) | Stop immediately. Tell the user: 'No project wiki found. Create an `.ai/wiki/` directory in your target project root before running capture.' Do not create the directory automatically. |

For field definitions and id conventions, see `REFERENCE.md`.
