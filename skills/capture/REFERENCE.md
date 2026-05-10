# capture — Reference

## Frontmatter fields

### Required

| Field | Type | Notes |
|---|---|---|
| `id` | string | `<project>:<type>:<slug>`. Immutable after creation. Never reuse a deleted slug. Prompt user if uncertain — never guess. |
| `title` | string | Human-readable. Sentence case. |
| `status` | enum | `draft` / `approved` / `archived`. Always `draft` on first write. |
| `created` | YYYY-MM-DD | Set at creation; never changed. |
| `updated` | YYYY-MM-DD | Set to today's date whenever any field or body content changes. Do not update if the page content is unchanged. (Exclude the `updated` field itself from any unchanged-content comparison to avoid circular dependency. The empty-diff guard applies on the UPDATE path only. Exception: if the current write is on the REPAIR path — malformed file detected in on-demand step 2 — always write regardless of diff state.) |

### Standard-optional

| Field | Type | Notes |
|---|---|---|
| `slug` | string | Inner slug only (no namespace). Include when the value would differ from the filename stem; omit otherwise. |
| `synced-at-commit` | string | Git SHA of the commit when this page was last verified against its source files. Managed exclusively by the sync skill — the capture skill never sets or removes this field under any conditions. Never set or remove this field. If already present in the file, preserve it unchanged — including on the REPAIR path: if the malformed file contains a readable `synced-at-commit` field, carry it into working state and write it through unchanged. See the sync skill for the rules governing when this field is set. |
| `describes-files` | string[] | Paths to source files this page tracks. Non-empty = code-tracking page; absent or empty = concept/decision page with no file-bound staleness. |
| `tags` | string[] | Categorization labels. |

### Extension fields

Any additional fields (`sources`, `related`, `supersedes`, `archived-reason`) pass through unchanged. Include them when the user or project convention requires them.

---

## Lifecycle states

| Status | Meaning |
|---|---|
| `draft` | Being written or awaiting review. AI always sets this on first write. |
| `approved` | Reviewed and trusted. Set by the user — never by the AI. When the capture skill updates a page whose status is `approved`, it preserves the status and displays this warning in the approval gate: `[WARNING: this page is currently approved — content will be updated but status preserved]`. Status is never automatically demoted by the capture skill — only the user can change it. |
| `archived` | No longer active. Requires `archived-reason` in the body or as a frontmatter field. |

---

## id convention

Format: `<project>:<type>:<slug>`

- `project`: short repo or product name (e.g. `memex`, `myproject`)
- `type`: `wiki` for knowledge entries; `active` for the ACTIVE.md pointer. `wiki` is the catch-all type for all knowledge, decision, concept, and code-tracking pages (including pages with `describes-files` populated). `active` is reserved exclusively for the ACTIVE.md pointer page. No other type values exist — do not invent new type values.
- `slug`: kebab-case; matches the filename stem by convention

Examples: `memex:wiki:capture-skill`, `myproject:wiki:auth-design`

**Immutability:** `id` is set at creation and never changed. If a slug must change, create a new page with a new id and archive the old one.

---

## Commit message formats

| Mode | Format |
|---|---|
| On-demand (single page) | `wiki: capture <slug> — <title>` |
| Session-end (batch) | `wiki: capture session — <W> pages` |

W is the count of distinct pages in the written-pages record for this run. Count each page once regardless of how many times it was written or validated. Skipped pages and pages that failed validation are excluded. Note: W differs from N (the candidate count displayed in session-end step 2). "This run" spans the full session from initial batch proposal through all re-entries triggered by session-end step 5, ending after all pages have been processed or skipped.

Example: `wiki: capture auth-design — Auth layer design decisions`

> **Note:** Commit messages use the Unicode em dash (U+2014, `—`). Before committing:
> 1. Run `git config i18n.commitEncoding`. If the command exits successfully (exit code 0) and the output is empty, `utf-8`, `utf8`, `UTF-8`, or `UTF8` — proceed with the em dash. If the command exits with a non-zero code, or returns any other value (e.g. `cp1252`, `latin-1`), substitute `--` (ASCII double-hyphen) for the em dash.
> 2. If the `git commit` command fails for any reason, show the git error output to the user, do not retry automatically, and do not mark the page as committed.
