---
name: memex:index:archive
description: Explicitly archive a raw payload to ~/.memex/raw/ via the Archivist. Normally invoked internally by memex:index:write — exposed for cases where archival is desired without indexing (e.g., evidentiary capture of inputs that aren't documents).
---

# memex:index:archive

## When to use

Rare. Most callers use `memex:index:write` instead, which archives + indexes in one call. Use this skill when you need to preserve a raw byte stream without producing an Index entry.

## Inputs

- `payload` — bytes (or string, will be UTF-8 encoded)
- `filename` — suggested filename; the actual stored path includes a hash suffix

## What happens

Archivist canonicalizes (line endings normalized, outer whitespace stripped), computes SHA-256, writes to `~/.memex/raw/<hash-prefix>/<stem>-<hash8>.<ext>`. Idempotent: same canonical payload → same path.

## Invocation

`scripts/agents/archivist.py:archive(payload, filename)`

Returns: `{"hash": "<sha256>", "path": "<absolute path>"}`
