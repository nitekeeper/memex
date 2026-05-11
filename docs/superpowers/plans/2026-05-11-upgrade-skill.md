# upgrade skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `upgrade` skill — a Memex-bundled skill that upgrades Memex within a consumer product by pulling the Memex git repo to a new tag, copying `dist/` into place, running schema migrations, and rebuilding the DB.

**Architecture:** Prose skill (SKILL.md + REFERENCE.md), no Python script. Structural tests verify file existence, line count, description length, and required section presence. The skill reads `memex_path` and `memex_dir` from the consumer project's `CLAUDE.md`.

**Tech Stack:** Python (pytest, python-frontmatter) for tests. Markdown for skill files.

---

### Task 1: Write failing structural tests

**Files:**
- Create: `tests/test_upgrade_skill.py`

- [ ] **Step 1: Write the test file**

```python
import pathlib
import frontmatter as fm

SKILL_MD = pathlib.Path(__file__).parent.parent / "skills" / "upgrade" / "SKILL.md"
REFERENCE_MD = pathlib.Path(__file__).parent.parent / "skills" / "upgrade" / "REFERENCE.md"


def test_skill_md_exists():
    """skills/upgrade/SKILL.md must exist."""
    assert SKILL_MD.exists(), "skills/upgrade/SKILL.md must exist"


def test_skill_md_under_150_lines():
    """SKILL.md must stay ≤150 lines."""
    assert SKILL_MD.exists(), "skills/upgrade/SKILL.md must exist"
    with open(SKILL_MD, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) <= 150, f"SKILL.md is {len(lines)} lines — must be ≤150"


def test_skill_description_under_1024_chars():
    """SKILL.md description frontmatter must be ≤1024 chars."""
    post = fm.load(str(SKILL_MD))
    desc = str(post.metadata.get("description", ""))
    assert len(desc) > 0, "description field is empty"
    assert len(desc) <= 1024, f"description is {len(desc)} chars — must be ≤1024"


def test_reference_md_exists():
    """skills/upgrade/REFERENCE.md must exist."""
    assert REFERENCE_MD.exists(), "skills/upgrade/REFERENCE.md must exist"


def test_skill_has_version_detection():
    """SKILL.md must reference MANIFEST for version detection."""
    with open(SKILL_MD, encoding="utf-8") as f:
        body = f.read()
    assert "MANIFEST" in body, "SKILL.md must reference MANIFEST.md for version detection"


def test_skill_has_approval_gate():
    """SKILL.md must require explicit user approval before making changes."""
    with open(SKILL_MD, encoding="utf-8") as f:
        body = f.read()
    assert "yes" in body.lower() and ("cancel" in body.lower() or "confirm" in body.lower()), \
        "SKILL.md must include a yes/cancel approval gate"


def test_skill_has_migration_step():
    """SKILL.md must address schema migration handling."""
    with open(SKILL_MD, encoding="utf-8") as f:
        body = f.read()
    assert "migrat" in body.lower(), "SKILL.md must mention migration handling"


def test_skill_has_rebuild_step():
    """SKILL.md must include a DB rebuild step after upgrade."""
    with open(SKILL_MD, encoding="utf-8") as f:
        body = f.read()
    assert "rebuild" in body.lower(), "SKILL.md must include a rebuild step"


def test_skill_references_memex_dir():
    """SKILL.md must reference memex_dir config input."""
    with open(SKILL_MD, encoding="utf-8") as f:
        body = f.read()
    assert "memex_dir" in body, "SKILL.md must reference memex_dir input"


def test_skill_references_memex_path():
    """SKILL.md must reference memex_path config input."""
    with open(SKILL_MD, encoding="utf-8") as f:
        body = f.read()
    assert "memex_path" in body, "SKILL.md must reference memex_path input"
```

- [ ] **Step 2: Run tests — verify RED**

```
cd C:\Users\user\Documents\Skills\memex
python -m pytest tests/test_upgrade_skill.py -v
```

Expected: 10 failures — all `FileNotFoundError` or `AssertionError` because the skill files don't exist yet.

- [ ] **Step 3: Commit the failing tests**

```
git add tests/test_upgrade_skill.py
git commit -m "test: add structural tests for upgrade skill (RED)"
```

---

### Task 2: Write SKILL.md

**Files:**
- Create: `skills/upgrade/SKILL.md`

- [ ] **Step 1: Create the skill file**

```markdown
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
```

- [ ] **Step 2: Run tests — verify the SKILL.md tests pass**

```
python -m pytest tests/test_upgrade_skill.py -v -k "not reference_md"
```

Expected: 9 pass, 1 fail (`test_reference_md_exists` — REFERENCE.md not written yet).

---

### Task 3: Write REFERENCE.md

**Files:**
- Create: `skills/upgrade/REFERENCE.md`

- [ ] **Step 1: Create the reference file**

```markdown
# upgrade — Reference

## Inputs

| Field | Source | Required | Description |
|---|---|---|---|
| `memex_path` | `CLAUDE.md` | yes | Absolute path to the Memex git repo on disk |
| `memex_dir` | `CLAUDE.md` | yes | Absolute path to the installed Memex directory in the product |

## Version detection

Current version is read from `<memex_dir>/MANIFEST.md`. The header line format is:

    # Memex vX.Y.Z — Release Manifest

Latest available version is the topmost result of:

    git -C <memex_path> tag --list "v*" --sort=-version:refname

## applied_migrations.txt

Tracks which SQL migrations have already been applied to `.ai/memex.db`. Lives at
`.ai/applied_migrations.txt`. One filename per line. Created on first migration run if absent.

## Error table

| Condition | Action |
|---|---|
| `memex_path` missing from `CLAUDE.md` | Stop — ask user to add it |
| `memex_dir` missing from `CLAUDE.md` | Stop — ask user to add it |
| `MANIFEST.md` not found in `memex_dir` | Stop — Memex may not be installed |
| `git fetch` fails | Stop — report git error |
| `git checkout` fails | Stop — do not proceed |
| Migration SQL fails | Stop — do not apply further migrations |
| `rebuild.py` fails | Report error — upgrade otherwise complete |

## Invocation

Typically called by the parent product's upgrade skill. Can also be invoked directly:

    upgrade memex
    update memex
```

- [ ] **Step 2: Run all tests — verify GREEN**

```
python -m pytest tests/test_upgrade_skill.py -v
```

Expected: 10 pass, 0 fail.

- [ ] **Step 3: Run full test suite — verify no regressions**

```
python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```
git add skills/upgrade/SKILL.md skills/upgrade/REFERENCE.md tests/test_upgrade_skill.py
git commit -m "feat: add upgrade skill — upgrade Memex in a consumer product"
```

---

### Task 4: Update ROADMAP.md and CHANGELOG.md

**Files:**
- Modify: `ROADMAP.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Mark upgrade skill complete in ROADMAP.md**

In `ROADMAP.md`, find the line:

    | ☐ | `upgrade-memex` skill | Consumer-side upgrade skill...

Replace with:

    | ✅ | `upgrade` skill | Consumer-side upgrade skill — bundled in dist/, reads memex_path + memex_dir from CLAUDE.md, git-based version detection, full dist/ copy, migration support, DB rebuild. 2026-05-11. |

- [ ] **Step 2: Add entry to CHANGELOG.md Unreleased section**

In `CHANGELOG.md`, add under `## Unreleased`:

```markdown
**upgrade skill**
- New skill: `skills/upgrade/` — upgrades Memex within a consumer product. Reads `memex_path`
  and `memex_dir` from `CLAUDE.md`, checks git tags for new versions, shows changelog excerpt,
  approval gate, git checkout, copies full `dist/`, runs schema migrations, rebuilds DB.
- 10 structural tests passing.
```

- [ ] **Step 3: Commit**

```
git add ROADMAP.md CHANGELOG.md
git commit -m "chore: mark upgrade skill complete in roadmap and changelog"
```
