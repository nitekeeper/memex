---
description: "Use when the user wants to review wiki entries for curation quality — approving drafts, archiving stale or superseded entries. Cadence: quarterly or on goal-drift. Do NOT use for writing or updating wiki content (use capture), checking file-bound staleness (use sync), or converting lessons to wiki entries (use propose-wiki-entry)."
---

# review-wiki — wiki curation pass

## Project detection

- **No `.ai/wiki/`** at any accessible root: stop. Tell the user: 'No project wiki found. Create `.ai/wiki/` before running review-wiki.'
- **Exactly one detectable project**: proceed. Announce: 'Reviewing wiki at `<path>/.ai/wiki/`.' No confirmation needed.
- **More than one detectable project**: ask the user which project. Wait for explicit choice.

A project is detectable if it contains `.ai/wiki/` at its root. Check each root at this fixed path only; do not recurse.

---

## Procedure

1. **Scan** `.ai/wiki/` for all `.md` files with parseable frontmatter.
   - Bucket by priority:
     - **Priority 1 — draft**: `status: draft` entries (need a curation decision)
     - **Priority 2 — stale**: `status: approved` entries where `describes-files` is non-empty (staleness shown as informational only — run `internal/sync/SKILL.md` to assess)
     - **Priority 3 — all others**: `status: approved` with no `describes-files` (already healthy; skip unless user requests full review)
   - Default pass: Priority 1 only. If no drafts found, report "No draft wiki entries to review." and offer to include Priority 2 if stale entries exist.

2. **Show candidate list** before any action:
   ```
   Found N draft wiki entries:
   1. <title> (.ai/wiki/<slug>.md)
   2. <title> (.ai/wiki/<slug>.md)
   Proceed? (yes / cancel)
   ```
   - **yes** → review each in order
   - **cancel** → stop, change nothing

3. **For each entry**, show a summary block and offer choices:
   ```
   --- Entry <n> of N ---
   Title: <title>
   File: .ai/wiki/<slug>.md
   Status: draft  |  Tags: [...]
   Created: <date>  |  Updated: <date>
   
   Action? (approve / archive / defer)
   ```
   - **approve** → Approve action
   - **archive** → ask "Archive reason?" (required). Wait for reason. → Archive action
   - **defer** → no change; continue to next entry
   - Any other message → treat as a clarifying question; re-show block after answering

4. **After all entries** → commit if any files changed (see REFERENCE.md commit format).

---

## Actions

### Approve

1. Update `status: draft` → `approved` in the file's frontmatter.
2. Update `updated` to today.
3. Stage: `git add .ai/wiki/<slug>.md`.

### Archive

1. Update `status` → `archived` in the file's frontmatter.
2. Add `archived-reason: <reason>` to frontmatter (or update it if already present).
3. Update `updated` to today.
4. Stage: `git add .ai/wiki/<slug>.md`.

---

## Error handling

See REFERENCE.md error table and commit message format.
