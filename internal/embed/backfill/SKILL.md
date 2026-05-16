---
name: memex:embed:backfill
description: Re-encode every documents row with `embedding IS NULL` using the currently-configured provider. Idempotent — non-NULL rows are untouched. Use after first configuring an embedding API key, or after ingesting documents while no provider was set.
---

# memex:embed:backfill

## When to use

You ingested some documents before configuring an embedding provider (so they have `embedding=NULL` in `index.db.documents`), then later set up `OPENAI_API_KEY` (or switched to Voyage / local). This skill catches up — fills in the missing embeddings so vector retrieval works for those rows too.

Idempotent: only NULL-embedding rows are touched. Documents already encoded with the current provider are left alone.

## Inputs

- (optional) `batch_size` — commit every N rows. Default 100. Higher = fewer commits, lossier on crash; lower = safer, more commits.
- (optional) `dry_run` — count and report, but don't encode or write. Default false.

## Recipe

### Step 1 — (optional) Dry run for visibility

```python
from scripts import embeddings
preview = embeddings.backfill_null(dry_run=True)
```

`preview` returns `{considered, encoded=0, errors=0, provider, model, dim, dry_run=True}`. Report this to the user as a preview: "Found X documents with NULL embeddings. Provider: <p>, model: <m>, dim: <d>. Proceed?" If batch is large, give the user a heads-up about API cost (especially with OpenAI).

### Step 2 — Run the backfill

```python
result = embeddings.backfill_null()  # or backfill_null(batch_size=N)
```

Returns `{considered, encoded, errors, provider, model, dim, dry_run=False}`. Per-row failures (rate-limit, network blip) are counted in `errors` but don't abort the batch — they remain `NULL` and can be retried by re-running.

### Step 3 — Report

```
Backfill complete (provider=<p>, model=<m>, dim=<d>):
  considered: <N>
  encoded:    <M>
  errors:     <E>    ← still-NULL rows; re-run to retry
```

If `errors > 0`, encourage the user to rerun. If `errors == considered`, the provider is probably mis-configured (no key, wrong model name) — surface the actual error from the first failed encode by reading the audit/log.

## Errors

- `RuntimeError: openai SDK is not installed` (or voyageai / sentence-transformers) — install the matching package or change `MEMEX_EMBEDDING_PROVIDER`.
- `RuntimeError: OPENAI_API_KEY / VOYAGE_API_KEY ... is not set` — provider-specific env-var requirements.
- All other per-row exceptions are caught and counted as `errors`; the batch continues.

## Notes

- Backfill uses the *currently-configured* provider. If you previously had embeddings from a different provider in non-NULL rows, those are NOT touched. Mixed-provider state on dim mismatches will return garbage from `embeddings.cosine`. Use `memex:embed:reembed` to regenerate everything under a single provider.
- This skill is pure Python — no Task tool dispatch, no LLM in the loop. Embeddings are model API calls; they're not subagent work.
- After successful backfill, `~/.memex/registry.json:__embedding_model__` reflects the active provider/model/dim.
