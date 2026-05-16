---
description: "Use when the user wants to check whether project-wiki pages that track source files are still accurate, or to review and update stale pages. Also use when the user invokes /sync. Do NOT use for writing new pages (use capture) or ingesting external sources (use meta:ingest-source)."
---

# sync — review and update stale project-wiki pages

## Project root detection

- Zero detectable projects (no `.ai/wiki/` found): stop. Tell user: 'No project wiki found. Create an `.ai/wiki/` directory in your target project root before running sync.'
- Exactly one: proceed. Announce: 'Writing to `<path>/.ai/wiki/`'
- More than one: ask the user which project. Wait for explicit choice.

---

## Explicit mode (/sync)

**Step 1.** Run `python scripts/sync.py .ai/` from the confirmed project root. Set the working directory to the confirmed project root before running. On non-zero exit: show stderr, stop.

**Step 2.** Parse the JSON report. If `stale` array is empty: report `All N tracked pages are current.` (N = `clean` array length). Done.

**Step 3.** For each entry in `stale` (one at a time, in order):

a. Read the page file at the `page` path. If missing: `Page file not found: <path> — skipping.` Continue.

b. Assess accuracy:
   - `STALE` entries: use the `diff` from each entry in `changed_files[]` — one diff per tracked file.
   - `NEVER_SYNCED` entries: `diff` is null — read current content of each file listed in the page's `describes-files` frontmatter directly (file read tool). Show current file content summary instead of a diff.

c. **Fast-forward** (STALE only — never for NEVER_SYNCED): if diff is purely cosmetic OR the AI is confident the page content fully reflects all changes → auto-stamp without user interaction. Announce: `Auto-synced: <title> — no content changes needed`. Stamp the page (see REFERENCE.md → Stamp procedure). Continue.

d. **Conflict gate** — show for all NEVER_SYNCED pages and any STALE page with doubt:
```
Page: .ai/wiki/<slug>.md  [STALE since <sha>]  or  [NEVER SYNCED]
Changed: <file> (+N / -N)  or  Current: <file summary>
Proposed update:
<AI-drafted revision of the page body>
~<N> lines
Approve? (yes / edit / skip)
```
   - **yes**: write the revised page body to disk, then stamp the page (REFERENCE.md → Stamp procedure). Continue.
   - **edit**: apply correction to the draft, re-show gate.
   - **skip**: leave page unchanged, do not stamp. Continue.
   - Match `yes`, `edit`, `skip` case-insensitively; treat `no` as `skip`. Any other message: treat as edit instruction — apply correction, re-show gate.

**Step 4.** After all pages processed:
- At least one page stamped: stage each stamped page individually by path (do not use `git add .ai/wiki/` or broad commands). Check em dash encoding (REFERENCE.md → Commit message format). Commit: `wiki: sync — N pages` (N = stamped count). On git failure: show error, do not retry; stamped files remain on disk uncommitted.
- Nothing stamped: report `No pages stamped — nothing to commit.` Do not commit.

---

## Error handling

| Situation | Action |
|---|---|
| `sync.py` exits non-zero | Show stderr, stop. Do not stamp or commit. |
| Page file missing at path in report | `Page file not found: <path> — skipping.` Continue. |
| `git commit` fails | Show git error, do not retry. Stamped files remain on disk uncommitted. |
| No `.ai/wiki/` directory | Stop: 'No project wiki found. Create an `.ai/wiki/` directory in your target project root before running sync.' |
| Unresolvable `synced-at-commit` SHA | `sync.py` exits non-zero with message identifying the bad SHA and page. See stderr output. |
