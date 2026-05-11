# Design Spec — `upgrade` skill

**Date:** 2026-05-11  
**Status:** approved

---

## What we're building

An `upgrade` skill that lives in Memex's `dist/` and is bundled inside any product that uses Memex as its memory layer. It is invoked by the parent product's own upgrade skill as a sub-step — end users never call it directly. Its job is to upgrade the Memex portion of the product: pull the new version from the Memex git repo, copy the full `dist/` into place, run any pending schema migrations, and rebuild the DB.

---

## Context

- Products (e.g. "development skill") bundle Memex entirely inside their own `dist/` — skills, scripts, docs, db schema, everything
- The product uses Memex as its memory system (`.ai/wiki/`, `lessons/`, DB)
- The Memex repo lives on disk at a path configured in the consumer project's `CLAUDE.md`
- Git tags (`v0.1.0`, `v0.2.0`, ...) and `CHANGELOG.md` in the Memex repo are the authoritative release info
- Upgrading Memex = pulling the repo + copying the full `dist/` to `memex_dir`

---

## Invocation chain

```
user
  → product's upgrade skill
      → upgrades product's own files
      → calls Memex's upgrade skill
          → pulls new Memex version from git
          → copies full dist/ to memex_dir
          → runs migrations
          → rebuilds DB
```

The `upgrade` skill is self-contained for everything Memex-related.

---

## Inputs

Both read from the consumer project's `CLAUDE.md` (or equivalent product config):

- `memex_path` — path to the Memex git repo on disk
- `memex_dir` — path to where Memex is installed in the product (skills, scripts, docs all live here)

---

## Procedure

### Step 1 — Detect versions

- Read current version from `<memex_dir>/MANIFEST.md`
- Run `git fetch` in `<memex_path>`
- List tags: `git tag --list "v*" --sort=-version:refname` — take the topmost as latest available

If current == latest: report "Already on vX.Y.Z — nothing to do." Stop.

### Step 2 — Show what's new

Extract the relevant `CHANGELOG.md` section from `<memex_path>` for the new version. Show:

```
Current:   vX.Y.Z
Available: vA.B.C

Changelog:
<excerpt>
```

### Step 3 — Approval gate

```
Upgrade Memex vX.Y.Z → vA.B.C? (yes / cancel)
```

Wait for explicit "yes". If cancel: stop.

### Step 4 — Checkout new version

```
git -C <memex_path> checkout vA.B.C
```

Stop on failure. Do not proceed with partial state.

### Step 5 — Copy full dist/

Copy all contents of `<memex_path>/dist/` into `<memex_dir>`. Overwrite existing files.

### Step 6 — Run schema migrations

For each `.sql` file in `<memex_dir>/db/migrations/` not yet recorded in `.ai/applied_migrations.txt`:

1. Run against `.ai/memex.db`
2. Append filename to `.ai/applied_migrations.txt`

Stop on migration failure. Do not apply further migrations.
Skip silently if no migration files exist.

### Step 7 — Rebuild DB

```
python <memex_dir>/scripts/rebuild.py .ai/
```

### Step 8 — Report

```
Upgraded Memex: vX.Y.Z → vA.B.C
Migrations applied: N
DB rebuilt.
```

---

## First real consumer — skill-atelier

Skill-atelier will be the first product to use this upgrade skill. After `upgrade` ships, skill-atelier needs to be set up as a proper Memex consumer:

- `memex_path` + `memex_dir` declared in its `CLAUDE.md`
- Full Memex `dist/` bundled (not loosely referenced)
- Self-improvement loop wired in

This is a separate task, done after the upgrade skill is complete.

---

## Anti-patterns

- Auto-invoking without being called by a parent upgrade skill or explicit user request
- Proceeding past a failed git checkout or migration
- Skipping the approval gate
- Copying individual directories instead of the full `dist/`
