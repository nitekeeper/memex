# Wiki Page Format

> **Status:** v0.1 — locked at synthesis session 2026-05-09. Supersedes the framework's `docs/PROJECT_WIKI_FORMAT.md` stub for Memex-managed project wikis.

## Purpose

Defines the file shape for entries in Memex-managed project wikis — the `.ai/wiki/` directory inside any project. Pages travel with their projects; Memex provides the tooling to read, index, and detect staleness across them.

## Page structure

A Memex page is a markdown file with a YAML frontmatter block. The body is free-form markdown — no required sections.

## Frontmatter fields

### Required

| Field | Type | Notes |
|---|---|---|
| `id` | string | Namespaced slug: `<project>:<type>:<slug>`. Immutable after creation. Never reuse a deleted slug. |
| `title` | string | Human-readable label. Sentence case. |
| `status` | enum | See lifecycle states below. |
| `created` | YYYY-MM-DD | Set at creation; never changed. |
| `updated` | YYYY-MM-DD | Updated on every write. |

### Standard-optional (Memex-defined)

These fields are understood by Memex tooling. Omitting them is valid; Memex treats the page as a concept/decision page with no file-bound staleness.

| Field | Type | Notes |
|---|---|---|
| `slug` | string | Inner slug only (no namespace prefix). Defaults to the filename stem if omitted. |
| `synced-at-commit` | string | Git SHA when the page was last verified against its source files. Null = not code-tracking. |
| `describes-files` | string[] | Paths to source files this page tracks. Empty or absent = no file-bound staleness. |
| `tags` | string[] | Categorization labels. Indexed in the DB for filtering. |

### Extension fields

Any additional fields (e.g. `sources`, `related`, `supersedes`, `archived-reason` used by the Skill Atelier methodology wiki) pass through unchanged. Memex parses fields matching known ID patterns into the `links` DB table; unknown fields are stored as raw frontmatter.

## Lifecycle states

`status` is a curation state — it reflects whether the page has been reviewed and is considered reliable. It is **not** a staleness state. Staleness is computed mechanically from `synced-at-commit` vs. git HEAD (see Staleness section below).

| Status | Meaning |
|---|---|
| `draft` | Being written or awaiting review. Not yet considered reliable. |
| `approved` | Reviewed and trusted. The canonical state for a healthy page. |
| `archived` | Kept intentionally but no longer active. Must have a reason documented in the body or an `archived-reason` extension field. |

## Staleness

A page is stale when its `describes-files` have changed since `synced-at-commit`. Staleness is computed, not stored:

```
stale = (describes-files is non-empty)
     AND (any describes-files path changed between synced-at-commit and HEAD)
```

A page with no `describes-files` is a concept/decision page. It has no file-bound staleness; its reliability is assessed by curation state (`status`) alone.

## Examples

**Minimal concept page:**
```yaml
---
id: myproject:wiki:auth-design
title: Auth design decisions
status: draft
created: 2026-05-09
updated: 2026-05-09
---
```

**Code-tracking page:**
```yaml
---
id: myproject:wiki:db-schema
title: Database schema
status: approved
created: 2026-05-09
updated: 2026-05-09
slug: db-schema
synced-at-commit: f88c1c6
describes-files: ["db/schema.sql", "db/migrations/"]
tags: [database, schema]
---
```

**With extension fields (framework methodology wiki usage):**
```yaml
---
id: wiki:grilling-pattern
title: Grilling pattern — relentless pre-implementation alignment
status: approved
created: 2026-05-09
updated: 2026-05-09
tags: [design, process, alignment]
sources: [source:mattpocock-skills]
related: [wiki:adr-selectivity-threshold, wiki:shared-language-pattern]
supersedes: []
archived-reason: ""
---
```

## Standard files inside `.ai/`

- `DIGEST.md` — one-page summary of the project: what it is, where it lives, key files.
- `ACTIVE.md` — current focus pointer. Uses this format with `describes-files: ["ROADMAP.md", "GOALS.md"]`.
- `wiki/` — topic entries (this format).
- `architecture/` — diagrams, system-shape docs.
- `sessions/` — project-specific session notes.
