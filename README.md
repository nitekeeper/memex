# Memex

**A personal knowledge runtime and shared memory plane for the agent fleet.**

Memex is the second-brain product of Skill Atelier (Product 1). It hosts your
personal knowledge — articles you read, notes you capture, syntheses you
produce — and serves as the shared memory layer for AI agents working on
your behalf.

## What's in v2.0

Three layers:

1. **Memex Brain** — opinionated second-brain skill layer. `ingest`, `ask`,
   `capture`, `lint`, `synthesize`. Stores articles, notes, and syntheses
   in `~/.memex/article.db`.
2. **Memex Index + 5 internal agents** — Librarian, Reference Librarian,
   Archivist, Database Administrator, Data Steward. Mandatory write-path
   gateway. Federated metadata, FTS5, embeddings, cross-store relationships.
3. **Memex Core** — CRUD substrate. Provisions and hosts arbitrary SQLite
   stores from consumer-supplied SQL migration files. Schema-agnostic.

24 internal procedures routed via the single `memex:run` skill, distributed via the Claude Code plugin. Per spec §8.0 only `memex:run` is registered with Claude Code — it routes natural-language user intents and agent-facing CRUD operations to the matching procedure on demand, keeping the plugin's skill-description footprint well under Claude Code's 1% budget.

## Installation

See the `INSTALL.md` inside the latest `dist/v*/` directory (built via `python -m scripts.release`). The release workflow attaches the same bundle to each [GitHub Release](https://github.com/nitekeeper/memex/releases).

For development:

```bash
python -m scripts.install
```

This bootstraps `~/.memex/`, seeds the 5 internal agents, creates the
default `article.db`, and registers everything in the global registry.

## Key design decisions (locked)

- Personal KM is the primary use case; project memory is a secondary
  capability via consumer stores (Atelier-style).
- SQLite-first; markdown is an export view, not the source of truth.
- Every document goes through the Librarian — no bypass.
- Eventually consistent across (Index, target store); Data Steward
  reconciles orphans.
- Open-ended `rel_type` vocabulary; Librarian's prompt is the consistency
  mechanism.
- Hybrid retrieval: FTS5 + vector embeddings from day one.

See `docs/specs/2026-05-16-memex-v2-redesign-design.md` for the full design.

## Layout

```
~/.memex/
├── agents.db       # roles + agents (5 Memex internal, plus your registered self)
├── index.db        # documents + relations + FTS5 + embeddings
├── article.db      # Brain's default store (articles + captures + syntheses)
├── registry.json   # registered stores
├── raw/            # Archivist's content-addressable raw archive
├── audits/         # Data Steward reports
└── legacy/         # v1 install (archived, not migrated)
```

## Status

See `CHANGELOG.md` for the latest release and version history.

## Layer awareness

This repo is Layer 2 (a Skill Atelier product). Framework changes live at
the Skill Atelier repo; product changes live here.
