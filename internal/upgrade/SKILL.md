---
description: >
  Use when upgrading Memex within a consumer product to a newer version. Reads memex_path
  and memex_dir from CLAUDE.md, checks available git tags, shows changelog, copies full
  dist/ into place, runs schema migrations, and rebuilds the DB.
  Do NOT auto-invoke — called by the parent product's upgrade skill or by explicit user request.
  Trigger on: "upgrade memex", "update memex", "memex upgrade".
---

# upgrade — upgrade Memex in a consumer product

## Purpose

Pull a new Memex version from the git repo, copy the full `dist/` into the product's Memex
directory, run any pending schema migrations, and rebuild the DB index.

## Inputs

Read both values from the consumer project's `CLAUDE.md`:

- `memex_path` — path to the Memex git repo on disk
- `memex_dir` — path to where Memex is installed in the product

If either is missing: stop and ask the user to add it to `CLAUDE.md` before proceeding.

## Procedure

### Step 1 — Detect versions

Read current version from `<memex_dir>/MANIFEST.md` (header line: `# Memex vX.Y.Z`).

Run:

    git -C <memex_path> fetch --tags

List available tags:

    git -C <memex_path> tag --list "v*" --sort=-version:refname

Take the topmost tag as the latest available version.

If current == latest: report "Already on vX.Y.Z — nothing to do." Stop.

### Step 2 — Show what's new

Read `<memex_path>/CHANGELOG.md`. Extract the section for the new version.

Show:

    Current:   vX.Y.Z
    Available: vA.B.C

    Changelog:
    <excerpt from CHANGELOG.md for vA.B.C>

### Step 3 — Approval gate

Show:

    Upgrade Memex vX.Y.Z → vA.B.C? (yes / cancel)

Wait for explicit "yes". If "cancel": stop.

### Step 4 — Checkout new version

    git -C <memex_path> checkout vA.B.C

Stop on failure. Do not proceed with partial state.

### Step 5 — Copy full dist/

Copy all contents of `<memex_path>/dist/` into `<memex_dir>`. Overwrite existing files.

### Step 6 — Run schema migrations

List `.sql` files in `<memex_dir>/db/migrations/`. For each not yet recorded in
`.ai/applied_migrations.txt`:

1. Run the SQL file against `.ai/memex.db`
2. Append the filename to `.ai/applied_migrations.txt`

Stop on migration failure. Do not apply further migrations.
Skip silently if no migration files exist.

### Step 7 — Rebuild DB

    python <memex_dir>/scripts/rebuild.py .ai/

### Step 8 — Report

    Upgraded Memex: vX.Y.Z → vA.B.C
    Migrations applied: N
    DB rebuilt.

## Anti-patterns

- Auto-invoking without being called by a parent upgrade skill or explicit user request
- Proceeding past a failed git checkout or migration
- Skipping the approval gate at Step 3
- Copying only skills/ instead of the full dist/
