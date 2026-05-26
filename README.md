# Memex

**A personal knowledge runtime and shared memory plane for the agent fleet.**

Memex hosts your personal knowledge — articles you read, notes you capture, syntheses you produce — and serves as a shared memory layer for AI agents working on your behalf. It is **plugin-agnostic**: any Claude Code plugin can register its own SQLite store with Memex and let its documents flow through the same indexing pipeline. Consumers like project-management or workspace plugins use Memex for durable memory; Memex doesn't know or care which plugin you wired in.

## A note on origins

Most of the code in this repository is developed and maintained collaboratively with [Claude Code](https://claude.com/claude-code). Commits are typically co-authored (`Co-Authored-By: Claude Opus …`), tests and refactors are AI-assisted, and the v2.0 design + implementation plans were pair-written (now captured in Memex itself; recoverable via git history pre-2026-05-26). Human-authored PRs are welcome; when reviewing changes, apply the usual AI-codegen review reflexes — most of it is clean, but the occasional confident-but-wrong section is worth a careful read.

## What Memex is

Three layers, one plugin:

1. **Memex Brain** — opinionated second-brain skill layer. `ingest`, `ask`, `capture`, `lint`, `synthesize`. Stores articles, free-form notes, and syntheses in `~/.memex/article.db`.
2. **Memex Index + 5 internal agents** — Librarian, Reference Librarian, Archivist, Database Administrator, Data Steward. Mandatory write-path gateway. Federated metadata, FTS5 full-text search, vector embeddings, and cross-store relationships.
3. **Memex Core** — CRUD substrate. Provisions and hosts arbitrary SQLite stores from consumer-supplied SQL migration files. Schema-agnostic; any consumer plugin can declare its own tables and let Memex own the storage and federated search.

24 internal procedures are routed via a single Claude-Code-visible skill, `memex:run`, which dispatches natural-language user intents and agent-facing CRUD operations to the matching procedure on demand. This keeps the plugin's skill-description footprint well under Claude Code's 1% budget.

## Installation

Memex has two audiences with different install paths.

### For consumers — using Memex in your Claude Code

You want to install Memex alongside your other Claude Code plugins and use it to remember things, search across stores, and let other plugins write to a shared memory plane.

1. **Install via your Claude Code marketplace.** Claude Code unpacks the bundle to `~/.claude/plugins/cache/<marketplace>/memex/<version>/` (it manages this path — do not place files manually). Each release ships an `INSTALL.md` inside the bundle.
2. **Restart Claude Code**, or invoke `/plugin reload memex` if your version supports it.
3. **Invoke `memex:run`** and express an intent in natural language (e.g., *"ingest this article"*, *"what do I know about X?"*, *"capture this thought"*).
   - On the very first invocation, `memex:run` Step 0 detects the missing `~/.memex/`, prints a consent block listing what will be created, and prompts `(y/n)`. Answer `y` and Memex bootstraps `~/.memex/` (seeds the 5 internal agents, creates `article.db`, writes `registry.json` and `config.json`). No separate install command is required.
   - On first use of any Brain operation you'll be prompted to register yourself as a human agent — one-time setup.

If you ever need to bootstrap manually (Step 0 is unreachable, broken `~/.memex/`, automated deployment), run:

```bash
python3 -m scripts.install
```

**Optional but recommended:** configure an embedding provider for hybrid retrieval (FTS5 + vector cosine). Memex works without one — FTS5 alone retrieves results — but the dashed-line search quality is meaningfully better with embeddings. See the bundle's `INSTALL.md` for provider options (`openai`, `voyage`, or local sentence-transformers) and the env vars each one expects.

### For developers — contributing to Memex itself

You want to hack on Memex, run the tests, send PRs, or fork it.

```bash
git clone https://github.com/nitekeeper/memex.git
cd memex
python3 -m pip install pytest ruff bandit pip-audit    # dev tooling
pytest tests/                                # run the full suite (~20s)
ruff check . && ruff format --check .        # lint + format
bandit -c pyproject.toml -r scripts internal skills db   # security
```

To bootstrap a working `~/.memex/` against your working tree:

```bash
python3 -m scripts.install
```

This creates `~/.memex/`, seeds the 5 internal agents, creates the default `article.db`, and registers everything in the registry — the same flow that runs on a consumer's first invocation, but driven from the source tree instead of an installed plugin.

To rebuild a distribution bundle from the source tree:

```bash
python3 -m scripts.bump 2.X.Y        # bump plugin.json + pyproject.toml + dist/
# edit CHANGELOG.md with an entry for v2.X.Y
git commit -am "release: bump to v2.X.Y"
git push                             # open PR, merge as usual
git tag v2.X.Y && git push --tags    # tag-triggered release workflow does the rest
```

PRs run a CI gate (lint, security, tests) — see `.github/workflows/ci.yml`. Branch protection on `main` blocks merges until all three pass.

Read these to get oriented as a contributor:

- `docs/CORE.md`, `docs/INDEX.md`, `docs/BRAIN.md`, `docs/PACKAGING.md` — per-layer acceptance docs (the tracked v2.0 contract).
- Locked architecture spec: see git history pre-2026-05-26 for the v2.0 design body, or query the dogfooded copy via `memex:run ask` (untracked in memex#22 — canonical store is Memex).
- `USER_GUIDE.md` — user-facing operations reference.
- `CHANGELOG.md` — version history.

## Key design decisions (locked)

- Personal knowledge management is the primary use case; project- or domain-specific memory is a secondary capability via consumer-registered stores.
- SQLite-first. Markdown is an export view, not the source of truth.
- Every document goes through the Librarian — no bypass paths.
- Eventually consistent across the (Index, target store) pair; Data Steward reconciles orphans.
- Open-ended `rel_type` vocabulary; the Librarian's prompt is the only consistency mechanism.
- Hybrid retrieval — FTS5 + vector embeddings — from day one. Embedding is best-effort; FTS5 always works.

Full design rationale: see git history pre-2026-05-26 for the v2.0 design body, or query via `memex:run ask` (untracked in memex#22).

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
