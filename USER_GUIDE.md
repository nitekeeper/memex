# Memex v2.0 — User Guide

## First-time setup

1. Install the plugin (see `dist/v2.2.0/INSTALL.md`).
2. Restart Claude Code.
3. Run `python -m scripts.install` (one-time bootstrap).
4. (Optional) Configure embeddings — see "Embeddings & retrieval" below.
   Memex works without an embedding provider; FTS5 alone retrieves results.

## How to invoke Memex

Per spec §8.0, Memex registers a single Claude Code skill: `memex:run`.
You don't invoke `memex:brain:ingest` or `memex:brain:ask` as
top-level skills — those names are not in `plugin.json`. Instead you
invoke `memex:run` and express your intent in natural language. The
plugin routes the intent to the matching internal procedure under
`internal/brain/<name>/SKILL.md`, reads it, and follows it. Examples:

- "ingest this article: <url or body>" → `internal/brain/ingest/SKILL.md`
- "ask my brain: what did I read about transformers?" → `internal/brain/ask/SKILL.md`
- "capture this thought: ..." → `internal/brain/capture/SKILL.md`
- "lint my brain" or "audit my brain" → `internal/brain/lint/SKILL.md`
- "synthesize across these sources: ..." → `internal/brain/synthesize/SKILL.md`

The procedure descriptions below name each operation by its logical
identifier (`memex:brain:ingest`, etc.) for clarity — the underlying
implementation lives at `internal/brain/<name>/SKILL.md`.

## Onboarding

The first time you invoke a Brain operation (ingest, capture, etc.) via
`memex:run`, Memex will prompt you to register a human agent:

> "What's your agent id? (lowercase, dashes; example: `human-user`)"
> "Display name?"
> "Role? (default: User; can be Researcher, Owner, Editor, or custom)"

Your agent is registered in `~/.memex/agents.db` and used for attribution
on every write.

## Daily skills

### `memex:brain:ingest` — add an article

Hands an article (with optional source URL) to the Librarian, who
classifies it, links it to related entries in your Index, and stores it
in `~/.memex/article.db`.

Re-ingesting the same content is a silent no-op (source-hash check).

### `memex:brain:ask` — query

Natural-language questions go through the Reference Librarian, who runs
hybrid FTS5 + vector retrieval across the entire Index (all stores) and
returns ranked, citation-ready results.

### `memex:brain:capture` — quick note

Lighter than `ingest` — no source URL, no hash check. For thoughts,
observations, snippets.

### `memex:brain:lint` — health check

Runs the Data Steward audit. Reports orphans, broken relations, drift.
Read-only; never auto-fixes. Resolve findings via
`memex:steward:reconcile-orphan`.

### `memex:brain:synthesize` — cross-document synthesis

Pass a list of source `index_id`s and a topic. The Synthesizer LLM
produces a unified prose synthesis with inline citations. Result is
indexed as a `synthesis` document.

## Embeddings & retrieval

`memex:brain:ask` (and the lower-level `memex:index:search`) use **hybrid retrieval** — FTS5 lexical search + vector cosine similarity. Embeddings are optional but improve recall for semantic queries.

### Provider configuration

Set the provider via env var (default if unset: `openai`):

```
$env:MEMEX_EMBEDDING_PROVIDER = "openai"  # or "voyage" or "local"
```

| Provider | Env var(s) required | Model (default) | Dim | Notes |
|---|---|---|---|---|
| `openai` | `OPENAI_API_KEY` | `text-embedding-3-small` | 1536 | Default. Most ecosystem-compatible. |
| `voyage` | `VOYAGE_API_KEY` | `voyage-3` | 1024 | Anthropic-recommended embedding partner. |
| `local` | (none) | `all-MiniLM-L6-v2` (sentence-transformers) | 384 | Zero-API-cost, offline. First call downloads ~80MB model. |

### What happens without any provider configured

If `embeddings.encode()` raises (no key, provider error, network unreachable), the Brain skills catch the exception and persist with `embedding = NULL`. The document is still ingested and FTS5-searchable. You lose vector cosine on that row until you backfill (below).

This means **Memex works fine with no embedding config at all** — you just get FTS5-only retrieval. Add a key when you want richer semantic recall.

### Backfilling NULL embeddings

If you've ingested documents without a key and later configure one, run:

```
memex:run → "backfill embeddings"   (routes to internal/embed/backfill/SKILL.md)
```

This re-encodes every `documents.embedding IS NULL` row using the current provider. Idempotent — non-NULL rows are left alone. Existing audits / Index / target stores are untouched.

### Re-embedding after a model change

If you switch providers (e.g., `openai` → `voyage`), existing 1536-dim embeddings are dimensionally incomparable with new 1024-dim embeddings. Cosine similarity returns garbage. To recover:

```
memex:run → "re-embed all"   (routes to internal/embed/reembed/SKILL.md)
```

This re-encodes EVERY row (not just NULLs) using the current provider, replacing whatever's there. Heavier than backfill — only run when you genuinely changed models. Memex tracks the active provider+model in `~/.memex/registry.json` under `__embedding_model__` and the re-embed skill detects mismatches.

## Working with multiple stores

Memex hosts more than just your Brain. If you have Atelier installed,
or any other consumer that uses Memex Core, each has its own store.
The Index spans them all.

You can ask cross-store questions: "what decisions did the team make
about authentication?" — the Reference Librarian queries the Index,
finds matches in your articles AND Atelier's decisions table, and
returns ranked results from both.

## Maintenance

### Periodic audit

Invoke `memex:run` and say "lint my brain" (Brain-scoped) or "audit
the full Memex Index" (full sweep). The plugin routes to
`internal/brain/lint/SKILL.md` or `internal/steward/audit/SKILL.md`.

Recommended monthly or after bulk ingest activity.

### Vacuum

Invoke `memex:run` and say "vacuum the `article` store" (or any
registered store name). Routes to `internal/dba/vacuum/SKILL.md`.

Reclaims space. Run during quiet periods.

### Backup

Copy `~/.memex/` and any `<repo>/.memex/` directories. SQLite files
are self-contained.

## Troubleshooting

### "Agent not registered"

You skipped onboarding. Run:
```
python -m scripts.onboarding register <id> <name> <role>
```

### "Unknown store"

The store name you used isn't in `~/.memex/registry.json`. Check with:
```
python -m scripts.registry list
```

### Audit reports orphans

Open the latest report in `~/.memex/audits/`. For each finding, invoke
`memex:run` and say e.g. "reconcile orphan idx-XYZ with action
delete-index"; it routes to
`internal/steward/reconcile-orphan/SKILL.md`.
