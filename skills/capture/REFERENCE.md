# capture — Reference

## Frontmatter fields

### Required

| Field | Type | Notes |
|---|---|---|
| `id` | string | `<project>:<type>:<slug>`. Immutable after creation. Never reuse a deleted slug. Prompt user if uncertain — never guess. |
| `title` | string | Human-readable. Sentence case. |
| `status` | enum | `draft` / `approved` / `archived`. Always `draft` on first write. |
| `created` | YYYY-MM-DD | Set at creation; never changed. |
| `updated` | YYYY-MM-DD | Set to today's date whenever any field or body content changes. Do not update if the page content is unchanged. |

### Standard-optional

| Field | Type | Notes |
|---|---|---|
| `slug` | string | Inner slug only (no namespace). Include when the value would differ from the filename stem; omit otherwise. |
| `synced-at-commit` | string | Git SHA when page was last verified against its source files. Set only if `describes-files` is non-empty; otherwise omit the field entirely. |
| `describes-files` | string[] | Paths to source files this page tracks. Non-empty = code-tracking page; absent or empty = concept/decision page with no file-bound staleness. |
| `tags` | string[] | Categorization labels. |

### Extension fields

Any additional fields (`sources`, `related`, `supersedes`, `archived-reason`) pass through unchanged. Include them when the user or project convention requires them.

---

## Lifecycle states

| Status | Meaning |
|---|---|
| `draft` | Being written or awaiting review. AI always sets this on first write. |
| `approved` | Reviewed and trusted. Set by the user — never by the AI. |
| `archived` | No longer active. Requires `archived-reason` in the body or as a frontmatter field. |

---

## id convention

Format: `<project>:<type>:<slug>`

- `project`: short repo or product name (e.g. `memex`, `myproject`)
- `type`: `wiki` for knowledge entries; `active` for the ACTIVE.md pointer
- `slug`: kebab-case; matches the filename stem by convention

Examples: `memex:wiki:capture-skill`, `myproject:wiki:auth-design`

**Immutability:** `id` is set at creation and never changed. If a slug must change, create a new page with a new id and archive the old one.

---

## Commit message formats

| Mode | Format |
|---|---|
| On-demand (single page) | `wiki: capture <slug> — <title>` |
| Session-end (batch) | `wiki: capture session — <N> pages` |

Example: `wiki: capture auth-design — Auth layer design decisions`

> **Note:** Commit messages use the Unicode em dash (U+2014, `—`). Verify your git environment handles UTF-8 commit messages.
