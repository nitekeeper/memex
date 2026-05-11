# Design Spec — `upgrade` skill

**Date:** 2026-05-11  
**Status:** approved

---

## What we're building

A `upgrade` skill that lives in Memex's `dist/` and is bundled inside any product that uses Memex as its memory layer. It is invoked by the parent product's own upgrade skill as a sub-step — end users never call it directly. Its job is to upgrade the Memex portion of the product: pull the new version from the Memex git repo, copy updated skill files into place, run any pending schema migrations, and rebuild the DB.

---

## Context

- Products (e.g. "development skill") bundle Memex skills inside their own `dist/`
- The product uses Memex as its memory system (`.ai/wiki/`, `lessons/`, DB)
- The Memex repo lives on disk at a path configured in the consumer project's `CLAUDE.md`
- Git tags (`v0.1.0`, `v0.2.0`, ...) and `CHANGELOG.md` in the Memex repo are the authoritative release info

---

## Invocation chain

```
user
  → product's upgrade skill
      → upgrades product's own skill files
      → calls Memex's upgrade skill
          → upgrades Memex skill files
          → runs migrations
          → rebuilds DB
```

The `upgrade` skill is self-contained for everything Memex-related.

---

## Inputs

- `memex_path` — path to the Memex git repo, read from the consumer project's `CLAUDE.md`
- `memex_skills_dir` — path to the installed Memex skills folder, read from the consumer project's `CLAUDE.md` (or equivalent product config)

---

## Procedure

### Step 1 — Detect versions

- Read current version from the bundled `MANIFEST.md` (same directory as the skill)
- Run `git fetch` in `<memex_path>`
- List tags: `git tag --list "v*" --sort=-version:refname` — take the topmost as latest available

If current == latest: report "Already on vX.Y.Z — nothing to do." Stop.

### Step 2 — Show what's new

- Extract the relevant `CHANGELOG.md` section for the new version
- Show:
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

### Step 5 — Copy updated skill files

Copy each skill subdirectory from `<memex_path>/dist/skills/` into `<memex_skills_dir>`. Overwrite existing files.

### Step 6 — Run schema migrations

For each `.sql` file in `<memex_path>/dist/db/migrations/` not yet in `.ai/applied_migrations.txt`:
1. Run against `.ai/memex.db`
2. Append filename to `.ai/applied_migrations.txt`

Stop on migration failure. Do not apply further migrations.

Skip silently if no migration files exist.

### Step 7 — Rebuild DB

```
python <memex_path>/dist/scripts/rebuild.py .ai/
```

### Step 8 — Report

```
Upgraded Memex: vX.Y.Z → vA.B.C
Migrations applied: N
DB rebuilt.
```

---

## Anti-patterns

- Auto-invoking without being called by a parent upgrade skill or explicit user request
- Proceeding past a failed git checkout or migration
- Skipping the approval gate
