# Roadmap — Memex

---

## Research phase

| Status | Item | Notes |
|---|---|---|
| ✅ | Ingest Karpathy | Three sources analyzed: Software 2.0, LLM OS, AutoResearch. See `sources/analyzed/2026-05-09-karpathy-*.md`. |
| ✅ | Ingest user's existing LLM wiki build | second-brain-blueprint analyzed 2026-05-09. SQLite crash-safety also ingested (WAL fix identified). |
| ✅ | Ingest Superpowers | Analyzed 2026-05-09. 14 skills; key findings: mandatory invocation, CSO description trap, TDD-for-documentation, minimal frontmatter. See `sources/analyzed/2026-05-09-superpowers-skill-system.md`. |
| ✅ | Synthesis session | Format + schema decisions locked 2026-05-09. Session notes: `sessions/notes/2026-05-09-memex-synthesis.md` (framework). |

## Design phase

| Status | Item | Notes |
|---|---|---|
| ✅ | Format & schema lock | `docs/WIKI_PAGE_FORMAT.md` + `db/schema.sql` locked 2026-05-09. Single page format, minimal core + extensible, 3-state status, normalized join tables. |
| ☐ | Spec written | `docs/MEMEX_SPEC.md` — what the product is, what it does, what it does not do. |

## Build phase

| Status | Item | Notes |
|---|---|---|
| ✅ | Rebuild script | `scripts/rebuild.py` — `connect()`, `parse_page()`, `load_page()`, `_insert_links()`, `rebuild()`, CLI. 13 tests passing. Smoke tested against real `.ai/`. |
| ✅ | `capture` skill v0 | `skills/capture/SKILL.md` + `REFERENCE.md`. Two-mode: on-demand + session-end. Approval gate. 2026-05-10. |
| ✅ | `sync` skill v0 | `skills/sync/SKILL.md` + `REFERENCE.md` + `scripts/sync.py`. Staleness detection via `synced-at-commit` + `describes-files`. 8 tests passing. 2026-05-10. |
| ✅ | `ask` skill v0 | `skills/ask/SKILL.md` + `REFERENCE.md` + `scripts/search.py`. FTS5-powered tiered knowledge resolution (memex → web → model). 11 tests passing. 2026-05-10. |
| ⏭️ | Self-improvement loop v0 | Lesson capture/review, wiki curation passes. |

## Validation phase

| Status | Item | Notes |
|---|---|---|
| ☐ | Dogfood replacement | Memex replaces Skill Atelier's rough `.ai/` and `wiki/` tooling. |
| ☐ | Tests passing | Validation suite for capture, sync, and staleness detection. |

## Release

| Status | Item | Notes |
|---|---|---|
| ☐ | v0.1 release | `dist/` cut with manifest; git tag. Requires dogfood validation. |

---

## Conventions

- ✅ done · ⏭️ next · ☐ planned · ⏸️ paused
- Completed items get a `DESIGN_NOTES.md` entry.
- Releases are logged in `CHANGELOG.md`, not here.
