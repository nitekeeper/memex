# Sync Skill v0 — Design Spec

**Date:** 2026-05-10
**Product:** Memex
**Status:** Approved — ready for implementation plan

---

## Goal

Build the `sync` skill: staleness detection and guided review workflow for Memex project-wiki pages that track source files via `describes-files` + `synced-at-commit`.

---

## File layout

```
skills/sync/
  SKILL.md        ≤100 lines — the AI procedure
  REFERENCE.md    git commands, stamp procedure, commit formats

scripts/sync.py   staleness detection script

tests/
  test_sync_script.py   pytest tests for sync.py + SKILL.md constraints
```

No `EXAMPLES.md` for v0. Add after the first refactor cycle.

---

## Approach

Approach B (selected): Python script + thin skill. `sync.py` does all mechanical git/file work and outputs a structured JSON report. `SKILL.md` reads the report and handles the human-facing review workflow. Detection logic is hidden behind the script interface.

**Rejected:**
- Approach A (pure skill): AI parses raw git output in-context — fragile, not testable.
- Approach C (DB-driven): requires a fresh `rebuild.py` run as a mandatory prerequisite — too fragile.

---

## Skill description (trigger text)

> Use when the user wants to check whether project-wiki pages that track source files are still accurate, or to review and update stale pages. Also use when the user invokes `/sync`. Do NOT use for writing new pages (use capture) or ingesting external sources (use meta:ingest-source).

---

## `sync.py` interface

**Invocation:**
```
python scripts/sync.py <ai_dir>
```

**Output:** JSON to stdout.

```json
{
  "head": "a1b2c3d",
  "stale": [
    {
      "page": ".ai/wiki/db-schema.md",
      "id": "memex:wiki:db-schema",
      "title": "Database schema",
      "state": "STALE",
      "synced_at_commit": "f88c1c6",
      "changed_files": [
        { "path": "db/schema.sql", "diff": "@@...", "lines_changed": 12 }
      ]
    },
    {
      "page": ".ai/wiki/auth-flow.md",
      "id": "memex:wiki:auth-flow",
      "title": "Auth flow",
      "state": "NEVER_SYNCED",
      "synced_at_commit": null,
      "changed_files": [
        { "path": "src/auth.py", "diff": null, "lines_changed": null }
      ]
    }
  ],
  "clean": [
    {
      "page": ".ai/wiki/capture-design.md",
      "id": "memex:wiki:capture-design",
      "title": "Capture skill design decisions",
      "state": "CLEAN",
      "synced_at_commit": "a1b2c3d",
      "changed_files": []
    }
  ],
  "untracked": [
    {
      "page": ".ai/wiki/grilling-pattern.md",
      "id": "memex:wiki:grilling-pattern",
      "title": "Grilling pattern"
    }
  ]
}
```

**Page states:**

| State | Condition |
|---|---|
| `STALE` | Has `describes-files` + `synced-at-commit`; at least one file changed since that commit |
| `NEVER_SYNCED` | Has `describes-files`; `synced-at-commit` absent or null |
| `CLEAN` | Has `describes-files` + `synced-at-commit`; no files changed since that commit |
| `UNTRACKED` | No `describes-files`; concept/decision page; never stale |

For `NEVER_SYNCED` pages: `diff` is `null` (no baseline commit). The skill reads the current file content directly via a file read.

**Error exits:** non-zero exit if `ai_dir` does not exist, git is unavailable, or `synced-at-commit` contains a SHA git cannot resolve. Error message written to stderr identifies the cause.

---

## SKILL.md workflow

### Project root detection

Identical to capture: zero/one/many detectable projects (`.ai/wiki/` present), same stop conditions, same "Writing to `<path>/.ai/wiki/`" announcement.

---

### Explicit mode (`/sync`)

1. **Run** `python scripts/sync.py .ai/` from the confirmed project root.
   - On error: show the stderr output, stop.

2. **No stale pages:** report `All N tracked pages are current.` Done.

3. **For each stale/never-synced page** (one at a time, in report order):

   a. Read the current page content.
   b. For `STALE`: read the diff string from `changed_files[].diff` in the JSON report.  
      For `NEVER_SYNCED`: `diff` is `null` in the report — read the current content of each `describes-files` path directly via a file read tool. This is intentional: there is no baseline commit to diff from.

   c. **Assess accuracy:** is the page content still accurate given the changes?

   - **Fast-forward** — diff is purely cosmetic (whitespace, comments, formatting only) OR the AI is confident the page content fully reflects all changes → auto-stamp without user interaction. Announce: `Auto-synced: <title> — no content changes needed`. Update `synced-at-commit` to HEAD and `updated` to today. Continue to next page.

   - **Conflict** — any doubt → show the guided edit gate:
     ```
     Page: .ai/wiki/<slug>.md  [STALE since f88c1c6]  or  [NEVER SYNCED]
     Changed: db/schema.sql (+12 / -3)
     <diff excerpt or current file summary for NEVER_SYNCED>
     Proposed update:
     <AI-drafted revision of the page body>
     ~<N> lines
     Approve? (yes / edit / skip)
     ```
     - **yes:** write the updated page, stamp `synced-at-commit` to HEAD, set `updated` to today.
     - **edit:** apply the stated correction to the current draft, re-show gate.
     - **skip:** leave page unchanged, do not stamp. Continue to next page.
     - Any other message: treat as an edit instruction — apply correction, re-show gate.

4. **Batch commit** after all pages are processed:
   - At least one page stamped: `wiki: sync — N pages` (apply em dash encoding check from `REFERENCE.md`).
   - Nothing stamped: report `No pages stamped — nothing to commit.` Do not commit.
   - Stage only stamped pages individually — do not use broad staging commands.

---

### Post-write reminder (capture integration)

Not a sync mode. A one-line note appended to capture's on-demand step 6 output when `describes-files` is non-empty on the written page:

> *"This page tracks files — run `/sync` to initialize staleness tracking."*

No invocation, no gate. `synced-at-commit` ownership remains exclusively with the sync skill.

---

### Assessment rule

Default conservative: **if in doubt, treat as conflict.**

The cost of a false conflict is one extra user approval. The cost of a false fast-forward is silently stale wiki content — which defeats the entire purpose of staleness tracking.

Fast-forward is reserved for diffs that are clearly cosmetic: whitespace normalization, comment rewording, file moves with no semantic change. Any structural or semantic change to a tracked file triggers the conflict gate.

---

## Error handling

| Situation | Action |
|---|---|
| `sync.py` exits non-zero | Show stderr, stop. Do not attempt any stamp or commit. |
| `synced-at-commit` SHA unresolvable | `sync.py` exits non-zero with message identifying the bad SHA and page. |
| Page file missing at path listed in report | Skip that page, warn: `Page file not found: <path> — skipping.` Continue with remaining pages. |
| `git commit` fails | Show the git error, do not retry. Leave stamped files on disk uncommitted for manual resolution. |
| No `.ai/wiki/` directory | Stop immediately. Tell the user: `No project wiki found. Create an .ai/wiki/ directory in your target project root before running sync.` |

---

## Testing

**File:** `tests/test_sync_script.py`

**~8 tests in three categories:**

### 1. Staleness detection (real git repo via `tmp_path`)

Build a minimal fixture repo using subprocess `git init`:

- Commit A: create `db/schema.sql` + `.ai/wiki/db-schema.md` with `describes-files: ["db/schema.sql"]` and `synced-at-commit: <SHA-A>`
- Commit B: modify `db/schema.sql`
- Run `sync.py` → assert `db-schema.md` appears in `stale` with non-empty `diff`

Cases:
- `test_stale_page_detected` — file changed since `synced-at-commit`
- `test_never_synced_page_detected` — `describes-files` set, no `synced-at-commit`
- `test_clean_page_not_stale` — file unchanged since `synced-at-commit`
- `test_untracked_page_ignored` — no `describes-files`, not in stale or clean

### 2. SKILL.md constraints

- `test_skill_md_under_100_lines`
- `test_skill_description_under_1024_chars`

### 3. Error handling

- `test_bad_ai_dir_exits_nonzero` — invalid `ai_dir` path → non-zero exit
- `test_unresolvable_sha_exits_nonzero` — `synced-at-commit: deadbeef` (bogus SHA) → non-zero exit, stderr contains the bad SHA

---

## Design decisions

| Decision | Rationale |
|---|---|
| Script + thin skill (Approach B) | Follows `rebuild.py` pattern; detection is testable and hidden from the skill |
| JSON output from `sync.py` | Reliable for skill to read; structured; easy to test assertions against |
| Fast-forward defaults conservative | False fast-forward = silently stale wiki; false conflict = one extra approval — asymmetric cost |
| `NEVER_SYNCED` treated as always-stale | `synced-at-commit` is a certification of accuracy; if never set, accuracy is unverified |
| `[NEVER SYNCED]` label in gate | Same flow as stale, but distinct label so user understands why the page is surfaced |
| Batch commit at end | Matches capture's session-end batch pattern; keeps git history clean |
| Asynchronous capture integration | Keeps capture and sync fully decoupled; `synced-at-commit` ownership stays with sync exclusively |
| Real git subprocess in tests | Matches project test philosophy (no mocks for external state); catches real git edge cases |

---

## What this spec does NOT cover (deferred)

- `sync --page <slug>` targeted single-page sync — deferred; full report mode covers v0 needs
- Cross-project sync (multiple `.ai/wiki/` roots) — deferred
- `search` skill — separate skill, separate spec
- `docs/MEMEX_SPEC.md` — product overview doc, written before v0.1 release
