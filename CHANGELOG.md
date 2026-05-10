# Changelog — Memex

All releases are logged here. Unreleased in-progress work is tracked in `ROADMAP.md`.

Format: [version] — date — summary.

---

## v0.1.0 — 2026-05-10

First release. Dogfood-validated against Skill Atelier (19 pages indexed, `rebuild.py` clean).

**Skills shipped:**
- `capture` — write or update wiki entries, on-demand and session-end modes, approval gate
- `sync` — staleness detection via `synced-at-commit` + `describes-files`
- `ask` — FTS5-powered tiered knowledge retrieval (memex → web → model)
- `capture-lesson` — lesson capture, inbox/feedback stream routing
- `review-lessons` — lesson review loop (promote / discard / defer), feedback-first priority
- `propose-wiki-entry` — converts promoted lessons into wiki entries
- `review-wiki` — curation pass (approve drafts, archive stale entries)

**Scripts:** `rebuild.py` (13 tests), `sync.py` (8 tests), `search.py` (11 tests)

**Format specs:** `WIKI_PAGE_FORMAT.md`, `LESSON_FORMAT.md`, `MEMEX_SPEC.md`

**Total tests:** 72 passing.
