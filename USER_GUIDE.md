# Memex — User Guide

A practical guide to using Memex day-to-day after it's installed. For install instructions and project background, see [`README.md`](README.md).

## First-time setup

1. Install Memex into your Claude Code (see the **For consumers** section of `README.md`, or the `INSTALL.md` inside the dist bundle).
2. Restart Claude Code.
3. Run `python -m scripts.install` once. This bootstraps `~/.memex/`: seeds the 5 internal agents, creates the default `article.db`, and registers everything in the registry.
4. (Optional) Configure embeddings — see "Embeddings & retrieval" below. Memex works fine without an embedding provider; FTS5 alone retrieves results, and you can add a provider any time.

## How to invoke Memex

Memex registers a **single** Claude Code skill: `memex:run`. There is no top-level `memex:brain:ingest` or `memex:brain:ask` skill — those names are not in `plugin.json`. Instead, you invoke `memex:run` and express your intent in natural language. The plugin reads the matching internal procedure under `internal/<category>/<name>/SKILL.md` and follows it.

Examples:

- *"ingest this article: <url or body>"* → `internal/brain/ingest/SKILL.md`
- *"ask my brain: what did I read about transformers?"* → `internal/brain/ask/SKILL.md`
- *"capture this thought: ..."* → `internal/brain/capture/SKILL.md`
- *"lint my brain"* or *"audit my brain"* → `internal/brain/lint/SKILL.md`
- *"synthesize across these sources: ..."* → `internal/brain/synthesize/SKILL.md`

The operations below are named by their logical identifier (`memex:brain:ingest`, etc.) for clarity, but you invoke them via natural language through `memex:run`.

## Onboarding

The first time you invoke a Brain operation (ingest, capture, etc.) via `memex:run`, Memex prompts you to register a human agent:

> "What's your agent id? (lowercase, dashes; example: `human-user`)"
> "Display name?"
> "Role? (default: User; can be Researcher, Owner, Editor, or custom)"

Your agent is registered in `~/.memex/agents.db` and used for attribution on every write.

## Daily operations

### `memex:brain:ingest` — add an article

Hands an article (with optional source URL) to the Librarian, who classifies it, links it to related entries in your Index, and stores it in `~/.memex/article.db`.

Re-ingesting the same content is a silent no-op (source-hash check).

### `memex:brain:ask` — query

Natural-language questions go through the Reference Librarian, who runs hybrid FTS5 + vector retrieval across the entire Index (every registered store) and returns ranked, citation-ready results.

### `memex:brain:capture` — quick note

Lighter than `ingest` — no source URL, no hash check. For thoughts, observations, snippets.

### `memex:brain:lint` — health check

Runs the Data Steward audit. Reports orphans, broken relations, drift. Read-only; never auto-fixes. Resolve findings via `memex:steward:reconcile-orphan`.

### `memex:brain:synthesize` — cross-document synthesis

Pass a list of source `index_id`s and a topic. The Synthesizer LLM produces a unified prose synthesis with inline citations. Result is indexed as a `synthesis` document.

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

This re-encodes every `documents.embedding IS NULL` row using the current provider. Idempotent — non-NULL rows are left alone. Existing audits, Index, and target stores are untouched.

### Re-embedding after a model change

If you switch providers (e.g., `openai` → `voyage`), existing 1536-dim embeddings are dimensionally incomparable with new 1024-dim embeddings. Cosine similarity returns garbage. To recover:

```
memex:run → "re-embed all"   (routes to internal/embed/reembed/SKILL.md)
```

This re-encodes every row (not just NULLs) using the current provider, replacing whatever's there. Heavier than backfill — only run when you genuinely changed models. Memex tracks the active provider+model in `~/.memex/registry.json` under `__embedding_model__` and the re-embed skill detects mismatches.

## Working across multiple stores

Memex hosts more than just your Brain. Any Claude Code plugin can register its own SQLite store with Memex Core (via `memex:core:create-store`) and write documents through the same Librarian pipeline. Common patterns: a project-management plugin registers a `tasks` and `decisions` schema; a research plugin registers a `sources` schema; a meeting plugin registers a `transcripts` schema. Each store keeps its own tables and PKs, but the Index spans every registered store.

This makes cross-store questions natural:

> *"what decisions did the team make about authentication?"*

The Reference Librarian queries the Index, finds matches across your articles, any project plugin's decisions table, any meeting plugin's transcripts table — and returns one ranked result set with citations pointing back to each source store.

If you're a plugin author and want to participate, see `internal/core/create-store/SKILL.md` and `internal/index/write/SKILL.md` for the registration and write contracts.

## Maintenance

### Periodic audit

Invoke `memex:run` and say *"lint my brain"* (Brain-scoped) or *"audit the full Memex Index"* (full sweep). Routes to `internal/brain/lint/SKILL.md` or `internal/steward/audit/SKILL.md` respectively.

Recommended monthly or after bulk ingest activity.

### Vacuum

Invoke `memex:run` and say *"vacuum the `article` store"* (or any registered store name). Routes to `internal/dba/vacuum/SKILL.md`. Reclaims space; run during quiet periods.

### Backup

Copy `~/.memex/` and any `<repo>/.memex/` directories. SQLite files are self-contained — straightforward filesystem copy, no special tooling.

## Troubleshooting

### "Agent not registered"

You skipped onboarding. Register manually:

```
python -m scripts.onboarding register <id> <name> <role>
```

### "Agent not registered: librarian-1" / "Unknown store: article"

You haven't run the one-time bootstrap. Run:

```
python -m scripts.install
```

This seeds the 5 internal agents and creates the default `article.db`.

### "Unknown store: <name>"

The store name you used isn't in `~/.memex/registry.json`. Check what's registered:

```
python -m scripts.registry list
```

### Audit reports orphans

Open the latest report in `~/.memex/audits/`. For each finding, invoke `memex:run` and say e.g. *"reconcile orphan idx-XYZ with action delete-index"*; routes to `internal/steward/reconcile-orphan/SKILL.md`.
