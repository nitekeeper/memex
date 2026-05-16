---
name: memex:embed:reembed
description: Re-encode EVERY documents row (NULL and non-NULL) using the currently-configured provider. Use after a deliberate provider or model change — old embeddings are dimensionally or semantically incomparable with new ones. Destructive — overwrites existing embeddings. Has a confirmation gate.
---

# memex:embed:reembed

## When to use

You changed `MEMEX_EMBEDDING_PROVIDER` (e.g., switched from openai → voyage) or the model env var (e.g., `MEMEX_OPENAI_MODEL` from `text-embedding-3-small` → `text-embedding-3-large`). Existing embeddings from the old config are incompatible with the new one — different dimensions, different vector space, different cosine semantics.

This skill regenerates every row's embedding under the current config. Heavier than `backfill` (touches every row, not just NULL ones), so it's gated by a confirmation prompt.

## Inputs

- (optional) `batch_size` — commit every N rows. Default 100.
- (optional) `dry_run` — preview the change without writes. Default false.
- (optional) `force` — skip the model-change-check warning. Default false.

## Recipe

### Step 1 — Detect drift between active config and what's recorded

```python
from scripts import embeddings
drift = embeddings.detect_model_change()
```

`drift` is `None` if the active provider/model matches what's recorded in `registry.json:__embedding_model__`, otherwise a dict:

```python
{"active":   {"provider": ..., "model": ..., "dim": ...},
 "recorded": {"provider": ..., "model": ..., "dim": ...},
 "changed":  ["provider"|"model"|"dim", ...]}
```

If `drift is None` and `force` is not set, ask the user: "No model change detected — active provider/model match what's recorded. Re-embed anyway? (y/n)". Only proceed on yes.

If `drift is not None`, summarize the change for the user:

```
Model change detected:
  was:  <recorded.provider> / <recorded.model> ({recorded.dim}-dim)
  now:  <active.provider>   / <active.model>   ({active.dim}-dim)
Changed: <changed list>

Re-embedding will overwrite all existing embeddings in
~/.memex/index.db. Continue? (y/n)
```

Wait for confirmation. STOP on no.

### Step 2 — (optional) Dry run

```python
preview = embeddings.reembed_all(dry_run=True)
```

`preview` includes `previous_recorded` so the user can see what's being replaced. Useful for cost-estimating against an API.

### Step 3 — Run the reembed

```python
result = embeddings.reembed_all()
```

Per-row errors are counted in `errors`; failed rows keep their previous (now-stale) embedding. Re-running picks up retries naturally.

### Step 4 — Report

```
Re-embed complete (provider=<p>, model=<m>, dim=<d>):
  was:        <previous_recorded.provider/model/dim>
  considered: <N>
  encoded:    <M>
  errors:     <E>
```

If `errors > 0`, urge the user to investigate — partial re-embeds mean some rows are still on the old model and will return bad cosine scores.

## Errors

Same provider-SDK / env-var errors as `backfill`. Per-row encoding errors are counted, not raised.

## Notes

- Destructive by definition: existing non-NULL embeddings are overwritten. There's no rollback. If you want to keep the old embeddings, snapshot `~/.memex/index.db` before running.
- API cost: this is "encode every document once." For an Index with ~1000 documents under OpenAI text-embedding-3-small, expect ~$0.02 (3-small is $0.02/M tokens; average doc ~500 tokens → ~500k tokens = $0.01-ish). Voyage and Local are cheaper / free respectively.
- If you only want to fill NULL rows (e.g., you just added a key and never had embeddings before), use `memex:embed:backfill` — it's idempotent and doesn't touch existing data.
- The recorded `__embedding_model__` in `registry.json` is updated automatically when `encode()` runs — no separate step needed to sync registry state.
