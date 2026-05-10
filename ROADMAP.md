# Roadmap — Memex

---

## Research phase

| Status | Item | Notes |
|---|---|---|
| ⏭️ | Ingest Karpathy | Frames self-improvement / LLM-as-OS ambition before format is locked. First source by design. |
| ☐ | Ingest user's existing LLM wiki build | Concrete prior art; most actionable input. |
| ☐ | Ingest Superpowers | Influential exemplar; deliberately last to avoid cargo-cult (GOALS.md anti-goals). |
| ☐ | Synthesis session | Compose research findings into design proposals; resolve format/schema decisions. |

## Design phase

| Status | Item | Notes |
|---|---|---|
| ☐ | Format & schema lock | Project-wiki file format + SQLite shape. Extends Skill Atelier Stage 1 schema. |
| ☐ | Spec written | `docs/MEMEX_SPEC.md` — what the product is, what it does, what it does not do. |

## Build phase

| Status | Item | Notes |
|---|---|---|
| ☐ | `capture` skill v0 | Writes a project-wiki page from a session. |
| ☐ | `sync` skill v0 | Staleness detection via `synced-at-commit` + `describes-files`. |
| ☐ | `search` skill v0 | FTS5-powered search across project wiki pages. |
| ☐ | Self-improvement loop v0 | Lesson capture/review, wiki curation passes. |

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
