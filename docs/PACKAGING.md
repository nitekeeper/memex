# Memex v2.0 Packaging

Plan 4 is the final wave of v2.0: packaging, install/upgrade, docs. This
document describes how the v2.0.0 release artifact is built, what it
contains, and how it is installed — framed by spec §8.0 (the single-skill
registration model).

## What ships in the bundle

`dist/v2.0.0/` is produced by `scripts/release.py` and contains:

- `plugin.json` — Claude Code plugin manifest. **Per spec §8.0 this
  registers exactly one skill: `memex:run`.** Claude Code's 1%
  skill-description budget makes per-procedure top-level registration
  infeasible (24 procedures would consume too much of the available
  context window and risk truncation), so all operations are reached
  through `memex:run`'s routing tables on demand.
- `scripts/` — Python CRUD + agent harness modules (`install.py`,
  `release.py`, `db.py`, `stores.py`, `registry.py`, `embeddings.py`,
  `upgrade_from_v1.py`, agent harness modules, etc.).
- `skills/run/SKILL.md` — the single registered skill. Its body holds
  the routing tables that map natural-language intent and agent-facing
  CRUD operations to the matching internal procedure.
- `internal/` — the 24 internal procedures, organized as
  `internal/<category>/<name>/SKILL.md`. Categories:
  - `internal/core/` — 10 CRUD primitives (`memex:core:*`).
  - `internal/index/` — 3 Index primitives (`memex:index:*`).
  - `internal/brain/` — 5 Brain procedures (`memex:brain:*`).
  - `internal/steward/` — 3 Data Steward procedures (`memex:steward:*`).
  - `internal/dba/` — 3 Database Administrator procedures (`memex:dba:*`).
  These files are NOT auto-loaded by Claude Code. They are read on
  demand by `memex:run` after its routing table has identified the
  matching procedure.
- `db/` — SQL migration files (`agents.sql`, `index.sql`, `brain.sql`,
  `migrations_table.sql`).
- `prompts/` — Librarian, Reference Librarian, and Synthesizer prompt
  templates.
- `manifest.json` — file inventory with SHA-256 hashes, byte counts,
  and build timestamp.
- `INSTALL.md` — install + upgrade instructions, generated at build
  time so the version number stays in sync.
- `README.md`, `USER_GUIDE.md`, `CHANGELOG.md` — top-level docs copied
  into the bundle for offline reference.

## Build

```bash
python -m scripts.release 2.0.0
```

Produces `dist/v2.0.0/`. The `dist/v*/` body is gitignored; only
`dist/v2.0.0/manifest.json` is tracked. This keeps the repo small but
preserves a verifiable record of every file shipped in the release
(path, SHA-256, byte count).

## Install flow

1. Bundle is placed in `~/.claude-code/plugins/memex/` (or the
   equivalent plugin directory for the user's Claude Code install).
2. Claude Code reloads the plugin (`/plugin reload memex` or a
   restart).
3. The user invokes `memex:run` and expresses an intent in natural
   language (e.g. "ingest this article: <url>"). On first invocation
   the plugin runs `install.run()`, which:
   - Archives v1 if `MEMEX_V1_PATH` is set (see "Upgrade from v0.1").
   - Creates `~/.memex/agents.db` and seeds the 5 internal Memex
     agents (Librarian, Reference Librarian, Archivist, Database
     Administrator, Data Steward).
   - Creates `~/.memex/index.db` (federated metadata + FTS5 +
     embeddings).
   - Creates `~/.memex/article.db` (Brain's default store).
   - Registers all stores in `~/.memex/registry.json`.
4. The onboarding prompt registers the human user as an agent in
   `~/.memex/agents.db`. Subsequent writes are attributed to that
   agent.

Subsequent invocations of `memex:run` skip the install step (it is
idempotent and short-circuits when the install footprint is already
present).

## Upgrade from v0.1

v0.1 stored data under `<project>/.ai/memex.db`. v2.0 is machine-global
at `~/.memex/`. The upgrade path is intentionally non-destructive and
non-migrating (per spec §5 design decision — v1 wiki content was a
project-scoped artifact, not a personal knowledge graph, and is best
re-ingested deliberately rather than auto-imported).

Steps:

1. Set `MEMEX_V1_PATH=<path-to-old-install>` (the directory containing
   `.ai/`).
2. Install the v2.0.0 plugin bundle.
3. On first `memex:run` invocation (which triggers `install.run()`):
   - `scripts/upgrade_from_v1.py:archive_v1()` detects the v1 install.
   - The contents of `<old>/.ai/` are copied to
     `~/.memex/legacy/v1-wiki/`.
   - An entry is appended to `~/.memex/legacy/upgrade-log.md`.
   - v2.0 then installs fresh alongside the archive.
4. The user re-ingests any v1 wiki entries that still matter via
   `memex:run` ("ingest this entry from my legacy wiki: …"), which
   routes to `internal/brain/ingest/SKILL.md`.

v1 wiki content is preserved verbatim under `~/.memex/legacy/v1-wiki/`
but is not part of the v2 Index until re-ingested.

## Acceptance criteria

1. `pytest tests/` is 100% green across all 4 plans' tests.
2. `python -m scripts.release 2.0.0` produces a valid bundle at
   `dist/v2.0.0/`.
3. `dist/v2.0.0/manifest.json` lists every file shipped with SHA-256
   and byte count, and has `version == "2.0.0"`.
4. `dist/v2.0.0/INSTALL.md` has correct instructions and references
   the correct version.
5. `README.md`, `USER_GUIDE.md`, and `CHANGELOG.md` reflect v2.0.0.
6. Bundle structure matches the spec §8.0 single-skill registration
   model:
   - `dist/v2.0.0/plugin.json` registers exactly one skill
     (`memex:run`).
   - `dist/v2.0.0/skills/run/SKILL.md` is present and contains
     routing tables covering all 24 procedures.
   - `dist/v2.0.0/internal/{core,index,brain,steward,dba}/` are all
     present with the expected procedure files underneath.
7. Git tag `v2.0.0` is created locally (push deferred to user
   decision).

## Why a single-skill registration model

Spec §8.0 mandates that Memex register exactly one Claude Code skill
(`memex:run`) regardless of how many internal operations it exposes.
The reasoning:

- Claude Code allots roughly 1% of the model context window to skill
  descriptions. Registering 24 separate skills with discriminating
  descriptions would consume a large fraction of that budget and risk
  truncation of other plugins' skills.
- All Memex operations share a common intent surface — the user
  almost never thinks "I want to call `memex:brain:ingest`"; they
  think "I want to save this article." A single routing entry point
  matches that mental model.
- Agents (the 5 internal Memex agents) call CRUD primitives by name
  through `memex:run`'s routing tables, not through Claude Code's
  skill dispatch. The routing tables live inside
  `skills/run/SKILL.md`'s body, where they cost nothing against the
  skill-description budget.

The 24 procedures themselves are full SKILL.md files at
`internal/<category>/<name>/SKILL.md`. They are first-class skill
definitions in every way except they are not registered with Claude
Code. `memex:run` reads them on demand and follows their body
verbatim.
