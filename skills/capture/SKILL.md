---
description: "Use when the user wants to capture a concept, decision, or summary as a project-wiki page — either on demand during a session (\"capture this as a wiki entry\") or at session end to review and propose pages from the conversation. Also use when the user invokes /capture. Do NOT use for ingesting external sources (use meta:ingest-source) or for staleness checking (use sync)."
---

# capture — write a project-wiki page

## Mode detection

- **On-demand** — user provides a topic, title, draft, or points to a decision from the conversation. Handle this first.
- **Session-end** — user invokes at end of session with no specific topic ("what should we capture?", `/capture` with no args).

Both modes share the approval gate. Commit behavior differs by mode.

**After detecting the mode and before executing any mode steps**, confirm the target project root:

- **Zero detectable projects** (no `.ai/wiki/` subdirectory found in any directory accessible from the current workspace): stop immediately. Tell the user: 'No project wiki found. Create an `.ai/wiki/` directory in your target project root before running capture.' Do not create the directory automatically. Do not proceed.
- **Exactly one detectable project**: proceed automatically. State the target before the first step: 'Writing to `<absolute-path-to-project>/.ai/wiki/`.' No user confirmation required.
- **More than one detectable project**: ask the user which project to target. Do not infer from recency, activity, or conversational context. Wait for an explicit choice.

A project is detectable if it has an `.ai/wiki/` subdirectory reachable from the current working directory or any workspace root currently open in the IDE (for example, a folder listed in a VS Code multi-root workspace file). If no IDE workspace context is available, treat the current working directory as the only root.

Once a project is confirmed, hold that project's `.ai/wiki/` directory as the target for every `.ai/wiki/` path reference throughout this run. All step references to `.ai/wiki/<slug>.md` mean `<that-project>/.ai/wiki/<slug>.md`.

---

## On-demand mode

1. **Extract content** from user input and/or conversation context:
   - `id`: `<project>:<type>:<slug>` — for valid `type` values see `REFERENCE.md` id convention; prompt if uncertain; never guess. After extracting `id`, scan all `.ai/wiki/*.md` files for any file whose frontmatter `id` field matches the extracted id and whose filename is not `<slug>.md`. If such a file is found, apply the `id already exists at a different path` row in the error handling table before proceeding.
   - `title`, `slug` (include only if it would differ from the filename stem; omit otherwise), `tags`, `status` (always `draft` on first write)
   - `describes-files` (only if this page tracks specific source files)
   - `body`: synthesized from conversation or polished from user draft

2. **Check for existing page** at `.ai/wiki/<slug>.md`:
   - Not found → prepare creation plan
   - Found and valid → read it; retain all existing frontmatter fields in working state. Extract the values of `status`, `created`, `updated`, and `synced-at-commit` (if present) specifically for use in the gate display (step 3) and preservation logic (step 4). Then prepare diff description (which fields and body sections change). Format the diff as one line per changed item: list each changed field by name; describe body changes as `body: <section name> updated` — if the body has no named sections, write `body: content updated`. Example: `[UPDATE: title changed, body: rationale section added]`. Do not show full before/after diffs in the gate display (the agent may compute a full diff internally to support the edit/correction path). If the comparison finds no changes to any field (excluding `updated`) and no body changes, record this explicitly as a no-changes result for the empty-diff guard in step 4. Show `[UPDATE: no content changes detected]` in the gate.
   - Found but malformed (YAML frontmatter cannot be parsed, or one or more required fields — `id`, `title`, `slug`, `status` — are absent or empty) → do not diff against the malformed content. Re-derive all frontmatter fields using step 1 extraction rules as if this were a NEW page — do not carry over any fields from the malformed file. Re-draft the body from the current conversation. Show gate as `[REPAIR: previous write failed — re-drafted from conversation]`. This path is exempt from the empty-diff guard in step 4.

3. **Show approval gate** before touching any file:
   ```
   Will write: .ai/wiki/<slug>.md
   Title: <title>
   Status: <status>  |  Tags: [...]
   ~<N> lines  (N = estimated line count of the page to be written)
   [NEW]  or  [UPDATE: <summary of changes>]  or  [REPAIR: previous write failed — re-drafted from conversation]
   [WARNING: this page is currently approved — content will be updated but status preserved]  ← include only when existing status is approved
   Approve? (yes / edit / skip / cancel)
   ```
   When constructing the gate: include the `[WARNING]` line only when this is an UPDATE and the existing page has `status: approved`. (The REPAIR path is implicitly exempt — the existing page's status is unreadable from a malformed file.)
   Evaluate responses in this order:
   If user says **yes**: proceed to step 4.
   If user says **cancel**, **abort**, or **quit**: treat as skip — stop; do not write anything.
   If user says **edit**: apply the stated correction to the current draft, return to step 3 to show the updated gate.
   If user says **skip**: stop; do not write anything.
   Any other message: treat as an edit instruction — interpret the full message as the correction, apply it to the current draft, return to step 3 with the updated gate.

4. **On approval**, write the file:
   - `created`: today if NEW; preserve existing value if UPDATE.
   - `updated`: today (YYYY-MM-DD) if content changed; preserve existing value if nothing changed. For this check, exclude the `updated` field itself from the diff comparison. This guard applies only on the UPDATE path — on the NEW path, always proceed to write regardless of diff state. If your content comparison in step 2 found no changes to any field other than `updated`, and no body content changed, do not write the file; tell the user "No changes detected — file not updated." and stop. **Exception: if step 2 flagged this page as a REPAIR path, always proceed to write regardless of diff state.**
   - For `created` and `updated`, use today's date in YYYY-MM-DD format — read from the `# currentDate` value in the session context if present; if absent, obtain it via the Bash tool (`date +%Y-%m-%d`) on POSIX systems or PowerShell (`Get-Date -Format yyyy-MM-dd`) on Windows.
   - `status`: preserve existing value on UPDATE — do not reset to `draft`.
   - `synced-at-commit`: never set or remove this field — if already present in the file, preserve it unchanged. The sync skill manages this field exclusively.
   - Conform to `docs/WIKI_PAGE_FORMAT.md` in the confirmed project root. If that file does not exist, use the field order and formatting conventions in `REFERENCE.md`. See `REFERENCE.md` for field details.

5. **Validate**: run `python scripts/rebuild.py .ai/` from the confirmed project root.
   - On error: show it, stop, do not commit. Leave file in place for inspection. Tell the user the message specified in the error handling table (rebuild.py errors in on-demand mode row). Note: a file left on disk after a `rebuild.py` failure may be malformed. On retry, step 2 checks the file's YAML frontmatter — if it is invalid or missing required fields, the REPAIR path applies. If the frontmatter is valid, step 2 treats the file as 'Found and valid' and proceeds through the normal diff gate.

6. **Auto-commit**: `wiki: capture <slug> — <title>` (apply the em dash encoding check from `REFERENCE.md` → Commit message formats before committing)

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
   If user says **approve all** (case-insensitive): proceed to step 3.
   If user says **approve individually** (case-insensitive): proceed to step 4.
   If user says **skip**: stop; do not write anything.
   If the user names specific pages to skip (e.g. "skip 2 and 4"): proceed directly to step 4, treating the named pages as already-skipped — do not show gates for those pages.
   Any other message: treat as an edit instruction for the candidate list — apply corrections to affected candidates (titles, slugs, removals), then re-display the updated batch list and re-evaluate responses using this same step 2 logic.

3. **Approve all**: Initialize the written-pages record as an empty list at the start of this step. Append each page's relative path to the record immediately after it is successfully written and validated (on-demand step 5 completion). This record is used throughout this run. Run steps 1–5 of on-demand mode for each page (using content extracted in step 1, not fresh user input; do not execute on-demand step 6 — the batch commit in step 6 below replaces it; if the `id` for any page is uncertain during batch execution, derive it from the slug rather than pausing to prompt — flag the derived id in the approval gate so the user can correct it). **Intervenes** means a message received while the agent is executing on-demand steps 1, 2, 4, or 5 for the current page — not while the approval gate (on-demand step 3) is actively awaiting a response (gate responses are handled by on-demand step 3's own branches). On intervention, pause immediately. Check whether the file for the in-progress page exists on disk:
   - If the file does **not yet exist on disk** for this page: present the approval gate (on-demand step 3) using the draft already computed — do not write yet. (This gate is referred to as the intervention gate for the current page.) (In session-end approve-all mode, on-demand step 3's 'any other message → edit' branch does not apply — use this intervention gate only for yes/edit/skip/cancel. Any other message: re-display the gate unchanged and remind the user: 'In approve-all mode this gate accepts only: yes / edit / skip / cancel.')
   - If the file **already exists on disk** for this page (written in this run): present the approval gate showing `[ALREADY WRITTEN — review?]` (written this run — the file on disk contains whatever was written; approving accepts this content and re-runs validation (on-demand step 5); skipping leaves the file on disk unvalidated); if the user approves, run on-demand step 5 (validate) and continue; if the user skips, validate the file immediately (run on-demand step 5) before continuing — do not leave an unvalidated file on disk.
   After handling the current page, continue with session-end step 4 (approve individually) for all remaining pages. The written-pages record populated during step 3 persists — do not reinitialize it; continue appending pages to it as each page is written and validated during step 4. Session-end step 6 (single batch commit) still applies at the end of the run.

4. **Approve individually**: Initialize the written-pages record as an empty list at the start of this step if it has not already been initialized (it may already exist if transitioning from a step 3 intervention). Append each page's relative path to the record immediately after it is successfully written and validated (on-demand step 5 completion). Run steps 1–5 of on-demand mode for each page (do not execute on-demand step 6 — the batch commit in step 6 below replaces it; if the `id` for any page is uncertain during batch execution, derive it from the slug rather than pausing to prompt — flag the derived id in the approval gate so the user can correct it); user approves or skips per page. **Intervention note**: If the user sends any message that is not yes, edit, skip, cancel, abort, or quit (cancel/abort/quit are treated as skip) during the approval gate for a page, treat it as an edit instruction for that page's draft — apply the correction and re-show the approval gate for that page. If the user sends a message while the agent is executing on-demand steps 1, 2, 4, or 5 (outside the gate window), pause immediately, present the approval gate for the current in-progress page, and apply this same approve-individually logic. If the user names a page that has already been written to disk in this run, show `[ALREADY WRITTEN — overwrite?]` (user explicitly requested re-processing — approving re-writes the file then validates; skipping leaves the file on disk as-is) instead of `[UPDATE]`.

5. **Mid-batch validation failure**: if `rebuild.py` fails on any page during a batch run, stop immediately. Do not commit anything. Display the current written-pages record as relative paths from the project root, one per line. This list is your written-pages record — do not reconstruct it from disk; use the record you have been maintaining throughout this run. Resolution means one of:
(a) The user indicates the issue is fixed (any message such as 'fixed', 'try again', or similar) — re-run `rebuild.py` on the failing file to verify; if it passes, add the file to the written-pages record and re-enter at session-end step 2 for the remaining unwritten pages; update N to reflect the reduced candidate set — do not carry forward the original N; retain the previously chosen approval mode — do not re-prompt for mode selection; upon re-entry, list numbering resets from 1 for the remaining pages — inform the user if numbering changes; if it still fails, re-display the three resolution paths.
(b) The user instructs you to skip the failing page (file stays on disk, user handles manually) or delete it (remove the file from disk) — apply the appropriate action, remove the page from the candidate set, and re-enter at session-end step 2 for remaining pages; update N to reflect the reduced candidate set — do not carry forward the original N; retain the previously chosen approval mode — do not re-prompt for mode selection; upon re-entry, list numbering resets from 1 for the remaining pages — inform the user if numbering changes.
(c) The user abandons the batch — stop entirely; do not commit; files written before the halt remain on disk uncommitted for the user to handle manually.
If the user is silent or sends an unrelated message, re-display the three resolution paths and wait.
The written-pages record persists across all re-entries — do not discard it; continue appending newly written-and-validated pages to it throughout the run including after re-entry. Do not re-propose pages in your written-pages record. If the user explicitly names a page from the written-pages record for re-processing (by slug, title, or list number as displayed in step 2), show `[ALREADY WRITTEN — overwrite?]` (user explicitly requested re-processing — approving re-writes the file then validates; skipping leaves the file on disk as-is) in the approval gate instead of `[UPDATE]`; if the user approves, proceed to on-demand steps 4 and 5 (write and validate), then continue the batch.

6. **One commit** for the batch (only when all approved-and-written pages pass validation):
   Evaluate the following guards in order:
   If the user chose path (c) (abandon) in step 5, do not commit — stop here.
   If any page encountered a validation failure in step 5 that was not subsequently resolved via path (a) or (b), do not commit — stop here.
   If no pages were written and validated (written-pages record is empty), do not commit — tell the user: 'No pages were written — nothing to commit.'
   Otherwise: `wiki: capture session — <W> pages` where W is the count of distinct pages in the written-pages record for this run (count each page once regardless of how many times it was written or validated; this is different from N in step 2 which is the candidate count). 'This run' spans the full session from initial batch proposal through all re-entries triggered by step 5, ending after all pages have been processed via step 4 or skipped.

---

## Error handling

| Situation | Action |
|---|---|
| `rebuild.py` errors in on-demand mode | Show error, stop, do not commit. Leave file in place for inspection. Tell the user: 'The file has been left on disk for inspection. Fix the issue, then re-invoke the capture skill for the same topic — step 2 will detect the malformed file automatically and apply the REPAIR path.' On re-invocation, no special user action is required beyond invoking capture again. |
| `rebuild.py` errors in session-end mode | See step 5 above — stop, list all written files as relative paths, re-enter at step 2. |
| `id` already exists at a different path | Flag before writing. Ask the user: (a) assign a new id to the new page — prompt the user for the new `id` only, apply it to the current draft, then re-enter at on-demand step 2 to check for an existing page at the new slug, then continue; (b) update the existing page at its current path — re-enter at on-demand step 2 using the existing page's path, treating the current draft as the proposed update; proceed through steps 2–6 normally so the diff gate is shown; (if the existing page is `approved`, on-demand step 3's WARNING gate line applies); (c) cancel — stop; do not write anything. Do not proceed until one option is explicitly chosen. |
| Required field missing | Prompt the user for the missing field. If the user provides a value, apply it and re-enter at on-demand step 1 to continue extraction. If the user cannot provide the value or declines, stop — do not write anything. Never guess `id`. |
| No detectable project (no `.ai/wiki/` directory found) | Stop immediately. Tell the user: 'No project wiki found. Create an `.ai/wiki/` directory in your target project root before running capture.' Do not create the directory automatically. (This mirrors the preamble zero-project guard; the preamble fires first.) |

For field definitions and id conventions, see `REFERENCE.md`.
