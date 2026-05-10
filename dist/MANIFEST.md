# Memex v0.1.0 — Release Manifest

**Released:** 2026-05-10  
**Status:** First release. Dogfood-validated against Skill Atelier (19 pages indexed).

---

## Skills

| Skill | File | Purpose |
|---|---|---|
| `capture` | `skills/capture/SKILL.md` | Write or update a wiki entry (on-demand or session-end) |
| `sync` | `skills/sync/SKILL.md` | Detect file-tracked staleness via `synced-at-commit` |
| `ask` | `skills/ask/SKILL.md` | FTS5-powered tiered knowledge retrieval |
| `capture-lesson` | `skills/capture-lesson/SKILL.md` | Capture lessons from a session (inbox/feedback streams) |
| `review-lessons` | `skills/review-lessons/SKILL.md` | Review draft lessons — promote, discard, or defer |
| `propose-wiki-entry` | `skills/propose-wiki-entry/SKILL.md` | Convert promoted lessons into wiki entries |
| `review-wiki` | `skills/review-wiki/SKILL.md` | Curation pass — approve drafts, archive stale entries |

Each skill has a paired `REFERENCE.md` with field definitions, error tables, and commit message formats.

---

## Scripts

| Script | Purpose |
|---|---|
| `scripts/rebuild.py` | Walk `.ai/`, rebuild `memex.db` from markdown |
| `scripts/sync.py` | Staleness check — list pages whose `describes-files` have changed |
| `scripts/search.py` | FTS5 search CLI — called by `ask` skill |

**Runtime dependency:** `pip install python-frontmatter` (see `scripts/requirements.txt`).

---

## Format specs

| File | Purpose |
|---|---|
| `docs/WIKI_PAGE_FORMAT.md` | Schema for `.ai/wiki/*.md` entries |
| `docs/LESSON_FORMAT.md` | Schema for `lessons/inbox/*.md` and `lessons/feedback/*.md` |
| `docs/MEMEX_SPEC.md` | What Memex is, does, and doesn't do |

---

## Database

`db/schema.sql` — SQLite schema for `memex.db`. Tables: `pages`, `links`, `page_files`, `page_tags`, `pages_fts` (FTS5). WAL + NORMAL safety. See schema comments for upgrade notes.

---

## Install

1. Copy `skills/` into your Claude Code skills directory.
2. Place `scripts/` and `db/` where your project can reach them.
3. `pip install python-frontmatter`
4. Create in your project: `.ai/wiki/`, `lessons/inbox/`, `lessons/feedback/`, `lessons/promoted/`
5. `python rebuild.py .ai/`

---

## What's not in this release

- No release tooling skill (planned for v0.2).
- No cross-project federation.
- No embedding-based search (FTS5 only at this version).
- `docs/MEMEX_SPEC.md` covers the full non-goals list.
