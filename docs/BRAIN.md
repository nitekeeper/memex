# Memex Brain (Plan 3)

Brain is Memex's opinionated second-brain layer. It owns `article.db`
and exposes five procedures for daily use.

## Invocation

Per spec §8.0, only `memex:run` is registered as a top-level Claude
Code skill. Brain procedures live at `internal/brain/<name>/SKILL.md`
and are reached on demand via the natural-language intent routing
table inside `skills/run/SKILL.md`. To use Brain, the user expresses
an intent to `memex:run` — e.g. "ingest this article", "ask about X",
"capture a thought" — and `memex:run` reads the matching procedure
file and follows it.

Users do not invoke `memex:brain:*` skills directly; they invoke
`memex:run` with natural-language intent, and the routing table
resolves the intent to the correct Brain procedure file.

## Procedures

| Procedure | Path | Purpose |
|---|---|---|
| memex:brain:ingest | internal/brain/ingest/SKILL.md | Add an external article (with hash-based rerun safety) |
| memex:brain:ask | internal/brain/ask/SKILL.md | Natural-language query, ranked results |
| memex:brain:capture | internal/brain/capture/SKILL.md | Free-form note |
| memex:brain:lint | internal/brain/lint/SKILL.md | Data Steward audit scoped to Brain |
| memex:brain:synthesize | internal/brain/synthesize/SKILL.md | Multi-source synthesis with provenance |

## Storage

`~/.memex/article.db` with three tables:
- `articles` — external sources, with `source_hash` + `raw_path`
- `captures` — free-form notes
- `syntheses` — generated synthesis documents with `inputs_json` provenance

All routed through the Librarian on write; through the Reference
Librarian on read.

## Onboarding

First Brain invocation triggers a one-time prompt to register the
human user as an agent. Subsequent invocations skip onboarding.

## Acceptance criteria

1. `pytest tests/` 100% green.
2. `install.run()` creates article.db.
3. First brain.ingest without registered human triggers onboarding.
4. brain.ingest is idempotent on identical content.
5. brain.ask returns results from index.db.
6. brain.synthesize produces a syntheses row with inputs_json provenance.
7. brain.lint generates an audit report.

## What Plan 3 ships beyond what brainstorming committed to

Adds `data_steward.reconcile_orphan` (was deferred from Plan 2). The
`reconcile_orphan` action supports `delete-index`, `repair`, and `note`
resolutions today; `reindex` is reserved for reverse-orphan handling and
raises `NotImplementedError` until Plan 4 re-embedding tooling lands.
`repair` was added in v2.4.0 to backfill link-missing orphans surfaced by
consumer-side sweeps (see Atelier 1.C correspondence).
