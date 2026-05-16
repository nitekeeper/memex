# Changelog — Memex

All releases are logged here. Unreleased in-progress work is tracked in `ROADMAP.md`.

Format: [version] — date — summary.

---

## v0.2.0 — 2026-05-16

**Major redesign.** Memex is no longer a project-scoped wiki. It is now a
personal knowledge runtime and shared memory plane for the agent fleet.

### Breaking changes

- `.ai/memex.db` is no longer used. v2 lives at `~/.memex/` (machine-global).
- v1 wiki content is NOT auto-migrated. v1 `.ai/` is archived to
  `~/.memex/legacy/v1-wiki/` on first v2 install (if `MEMEX_V1_PATH` is set).
  Re-ingest manually via `memex:brain:ingest`.
- Self-improvement loop skills (`capture-lesson`, `review-lessons`,
  `propose-wiki-entry`, `review-wiki`) are dropped from Brain. Lessons-as-a-
  consumer is a future project.
- `synced-at-commit` git-anchored staleness is no longer load-bearing. It can
  return as a consumer-specific column if needed.

### Added

- **Three-layer architecture:** Memex Brain (5 skills) / Memex Index +
  5 internal agents / Memex Core (10 CRUD skills).
- **Five Memex-internal agents:** Librarian (Dr. Lakshmi Iyer-Ranganathan),
  Reference Librarian (Dr. Eleanor Whitfield), Archivist (Dr. Heinrich
  Mühlbauer), Database Administrator (Dr. Rajesh Subramanian), Data
  Steward (Dr. Ingrid Bergström).
- **Federated Index** (`~/.memex/index.db`): documents + relations + FTS5 +
  embeddings. Mandatory write-path gateway via the Librarian.
- **Hybrid retrieval** (FTS5 + vector cosine) via Reference Librarian.
  OpenAI `text-embedding-3-small` default; pluggable provider.
- **Content-addressable raw archive** (`~/.memex/raw/`) via Archivist.
- **Multi-store substrate.** Core hosts arbitrary SQLite stores from
  consumer-supplied SQL migrations. Atelier and any future consumer share
  the substrate.
- **24 internal procedures** spanning `memex:core:*`, `memex:index:*`,
  `memex:brain:*`, `memex:steward:*`, `memex:dba:*` — all reached via
  `memex:run`'s routing table (see "Single-skill registration model"
  below).
- **Single-skill registration model.** Only `memex:run` is registered
  in `plugin.json`. All 24 operations live as internal procedures
  (`internal/<category>/<name>/SKILL.md`) discovered through
  `memex:run`'s routing table. This avoids Claude Code's 1%
  skill-description budget truncation.
- **Eventually consistent** atomicity contract between Index and target
  stores; Data Steward reconciles orphans via audit.

### Changed

- Storage model is SQLite-first. Markdown is a derived export view.
- Cold-start cost reduced significantly: no ops-file routing, no `hot.md`,
  no response-footer compliance tax.
- Plugin remains a Claude Code custom plugin, globally accessible from any
  session regardless of working directory.

### Removed

- Obsidian integration. Memex v2 is Claude Code-native.
- Web-Clipper-driven ingestion. `memex:brain:ingest` accepts payloads
  directly (URL, body, or both).
- The `!! command` syntax. Skills are invoked through Claude Code's
  standard skill mechanism.

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
