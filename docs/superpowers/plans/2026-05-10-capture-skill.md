# Memex `capture` Skill v0 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `capture` skill — a two-mode AI instruction file that lets an agent write or update Memex-format project-wiki pages from a session, with an approval gate before every write.

**Architecture:** Two markdown files (`SKILL.md` + `REFERENCE.md`) in `skills/capture/`. `SKILL.md` (≤100 lines) contains the on-demand and session-end procedures plus an error table. `REFERENCE.md` contains field definitions, lifecycle states, id convention, and commit formats — pulled in only when the agent needs them. Validation: a pytest test confirms a sample capture output passes `parse_page()` and `rebuild()`, and that `SKILL.md` satisfies the ≤100-line and ≤1024-char description constraints.

**Tech Stack:** Markdown (skill files), Python 3.11+ + pytest 8.x + python-frontmatter 1.x (validation tests), existing `scripts/rebuild.py` (format contract enforcer).

---

## Scope note

This is Plan 2 of 3 for the Memex build phase. Plan 1 (rebuild script) is complete. Plan 3 covers the `sync` skill.

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `skills/capture/SKILL.md` | Create | On-demand + session-end procedures, approval gate, error table |
| `skills/capture/REFERENCE.md` | Create | Field definitions, lifecycle states, id convention, commit formats |
| `tests/fixtures/capture-output/.ai/wiki/capture-design.md` | Create | Sample capture output — format contract fixture |
| `tests/test_capture_skill.py` | Create | Validates fixture parses + rebuilds cleanly; checks SKILL.md constraints |
| `ROADMAP.md` | Modify | Mark capture skill v0 ✅; advance sync to ⏭️ |
| `.ai/ACTIVE.md` | Modify | Point to sync skill v0 as next |

---

### Task 1: Validation tests and fixture

Write the fixture and tests first — they define the format contract the skill must produce, and the constraint tests will fail (RED) until Task 3 creates `SKILL.md`.

**Files:**
- Create: `tests/fixtures/capture-output/.ai/wiki/capture-design.md`
- Create: `tests/test_capture_skill.py`

- [ ] **Step 1: Create the fixture — a sample page the capture skill would produce**

Create `tests/fixtures/capture-output/.ai/wiki/capture-design.md`:

```markdown
---
id: memex:wiki:capture-design
slug: capture-design
title: Capture skill design decisions
status: draft
created: 2026-05-10
updated: 2026-05-10
tags: [skill, capture, design]
---

This page records the design decisions made for the `capture` skill v0.

The skill uses a single entry point with two intent-detected modes: on-demand and session-end.
```

- [ ] **Step 2: Write the tests**

Create `tests/test_capture_skill.py`:

```python
import os
import pathlib
import sqlite3
import frontmatter as fm

from rebuild import parse_page, rebuild

SCHEMA_PATH = str(pathlib.Path(__file__).parent.parent / "db" / "schema.sql")
FIXTURE_AI_DIR = str(
    pathlib.Path(__file__).parent / "fixtures" / "capture-output" / ".ai"
)
FIXTURE_PAGE = str(
    pathlib.Path(__file__).parent
    / "fixtures" / "capture-output" / ".ai" / "wiki" / "capture-design.md"
)
SKILL_MD = str(
    pathlib.Path(__file__).parent.parent / "skills" / "capture" / "SKILL.md"
)


def test_capture_output_parses_correctly():
    """A page the capture skill would produce must pass parse_page()."""
    page = parse_page(FIXTURE_PAGE)
    assert page["id"] == "memex:wiki:capture-design"
    assert page["title"] == "Capture skill design decisions"
    assert page["status"] == "draft"
    assert page["slug"] == "capture-design"
    assert page["project"] == "memex"
    assert page["tags"] == ["skill", "capture", "design"]
    assert page["synced_at_commit"] is None
    assert page["describes_files"] == []
    assert "capture skill" in page["body"]


def test_capture_output_rebuilds_cleanly(tmp_path):
    """A page the capture skill would produce must pass rebuild()."""
    db_path = str(tmp_path / "memex.db")
    rebuild(FIXTURE_AI_DIR, db_path, SCHEMA_PATH)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    count = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    assert count == 1
    row = conn.execute("SELECT id FROM pages").fetchone()
    assert row["id"] == "memex:wiki:capture-design"
    conn.close()


def test_skill_md_under_100_lines():
    """SKILL.md must stay ≤100 lines per wiki:skill-file-structure."""
    with open(SKILL_MD, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) <= 100, f"SKILL.md is {len(lines)} lines — must be ≤100"


def test_skill_description_under_1024_chars():
    """SKILL.md description field must stay ≤1024 chars per wiki:skill-file-structure."""
    post = fm.load(SKILL_MD)
    desc = str(post.metadata.get("description", ""))
    assert len(desc) > 0, "description field is empty"
    assert len(desc) <= 1024, f"description is {len(desc)} chars — must be ≤1024"
```

- [ ] **Step 3: Run tests to confirm RED state**

Run from the Memex repo root:
```
pytest tests/test_capture_skill.py -v
```

Expected:
- `test_capture_output_parses_correctly` — PASS
- `test_capture_output_rebuilds_cleanly` — PASS
- `test_skill_md_under_100_lines` — FAIL (`FileNotFoundError`: SKILL.md doesn't exist yet)
- `test_skill_description_under_1024_chars` — FAIL (`FileNotFoundError`: SKILL.md doesn't exist yet)

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/capture-output/ tests/test_capture_skill.py
git commit -m "test: capture skill validation fixture and constraint tests"
```

---

### Task 2: Write REFERENCE.md

**Files:**
- Create: `skills/capture/REFERENCE.md`

- [ ] **Step 1: Create skills/capture/ directory and write REFERENCE.md**

Create `skills/capture/REFERENCE.md`:

```markdown
# capture — Reference

## Frontmatter fields

### Required

| Field | Type | Notes |
|---|---|---|
| `id` | string | `<project>:<type>:<slug>`. Immutable after creation. Never reuse a deleted slug. Prompt user if uncertain — never guess. |
| `title` | string | Human-readable. Sentence case. |
| `status` | enum | `draft` / `approved` / `archived`. Always `draft` on first write. |
| `created` | YYYY-MM-DD | Set at creation; never changed. |
| `updated` | YYYY-MM-DD | Updated on every write. |

### Standard-optional

| Field | Type | Notes |
|---|---|---|
| `slug` | string | Inner slug only (no namespace). Defaults to filename stem if omitted. |
| `synced-at-commit` | string | Git SHA when page was last verified against its source files. Set only if `describes-files` is non-empty; otherwise omit the field entirely. |
| `describes-files` | string[] | Paths to source files this page tracks. Absent or empty = concept/decision page with no file-bound staleness. |
| `tags` | string[] | Categorization labels. |

### Extension fields

Any additional fields (`sources`, `related`, `supersedes`, `archived-reason`) pass through unchanged. Include them when the user or project convention requires them.

---

## Lifecycle states

| Status | Meaning |
|---|---|
| `draft` | Being written or awaiting review. AI always sets this on first write. |
| `approved` | Reviewed and trusted. Set by the user — never by the AI. |
| `archived` | No longer active. Requires `archived-reason` in the body or as a frontmatter field. |

---

## id convention

Format: `<project>:<type>:<slug>`

- `project`: short repo or product name (e.g. `memex`, `myproject`)
- `type`: `wiki` for knowledge entries; `active` for the ACTIVE.md pointer
- `slug`: kebab-case; matches the filename stem by convention

Examples: `memex:wiki:capture-skill`, `myproject:wiki:auth-design`

**Immutability:** `id` is set at creation and never changed. If a slug must change, create a new page with a new id and archive the old one.

---

## Commit message formats

| Mode | Format |
|---|---|
| On-demand (single page) | `wiki: capture <slug> — <title>` |
| Session-end (batch) | `wiki: capture session — <N> pages` |
```

- [ ] **Step 2: Commit**

```bash
git add skills/capture/REFERENCE.md
git commit -m "feat: capture skill REFERENCE.md — field definitions and id convention"
```

---

### Task 3: Write SKILL.md

**Files:**
- Create: `skills/capture/SKILL.md`

- [ ] **Step 1: Write SKILL.md**

Create `skills/capture/SKILL.md`:

```markdown
---
description: "Use when the user wants to capture a concept, decision, or summary as a project-wiki page — either on demand during a session (\"capture this as a wiki entry\") or at session end to review and propose pages from the conversation. Also use when the user invokes /capture. Do NOT use for ingesting external sources (use meta:ingest-source) or for staleness checking (use sync)."
---

# capture — write a project-wiki page

## Mode detection

- **On-demand** — user provides a topic, title, draft, or points to a decision from the conversation. Handle this first.
- **Session-end** — user invokes at end of session with no specific topic ("what should we capture?", `/capture` with no args).

Both modes share the approval gate and commit logic.

---

## On-demand mode

1. **Extract content** from user input and/or conversation context:
   - `id`: `<project>:<type>:<slug>` — prompt if uncertain; never guess
   - `title`, `slug`, `tags`, `status` (always `draft` on first write)
   - `describes-files` (only if this page tracks specific source files)
   - `body`: synthesized from conversation or polished from user draft

2. **Check for existing page** at `.ai/wiki/<slug>.md`:
   - Not found → prepare creation plan
   - Found → read it; prepare diff description (which fields and body sections change)

3. **Show approval gate** before touching any file:
   ```
   Will write: .ai/wiki/<slug>.md
   Title: <title>
   Status: draft  |  Tags: [...]
   ~<N> lines
   [NEW] or [UPDATE: <summary of changes>]
   Approve? (yes / edit / skip)
   ```
   If user says **edit**: apply correction, re-enter step 1, show gate again.

4. **On approval**, write the file:
   - `created` and `updated`: today's date (YYYY-MM-DD)
   - `synced-at-commit`: set only if `describes-files` is non-empty; otherwise omit
   - Conform to `docs/WIKI_PAGE_FORMAT.md`. See `REFERENCE.md` for field details.

5. **Validate**: run `python scripts/rebuild.py .ai/`
   - On error: show it, stop, do not commit. Leave file in place for inspection.

6. **Auto-commit**: `wiki: capture <slug> — <title>`

---

## Session-end mode

1. **Review conversation.** Find: decisions made, patterns named, constraints locked, concepts defined. Skip anything already wiki-ified or too ephemeral for the next session.

2. **Propose a batch list** before touching any file:
   ```
   Found N candidates:
   1. .ai/wiki/<slug>.md — "<title>" [NEW]
   2. .ai/wiki/<slug>.md — "<title>" [UPDATE: <summary>]
   Approve all / approve individually / skip?
   ```

3. **Approve all**: run steps 1–5 of on-demand mode for each page in sequence.

4. **Approve individually**: show the per-page gate for each; user approves or skips.

5. **One commit** for the batch: `wiki: capture session — <N> pages`

---

## Error handling

| Situation | Action |
|---|---|
| `rebuild.py` errors after write | Show error, stop, do not commit. Leave file for inspection. |
| `id` already exists at a different path | Flag before writing; do not proceed until resolved. |
| Required field missing | Prompt user; never guess `id`. |

For field definitions and id conventions, see `REFERENCE.md`.
```

- [ ] **Step 2: Run the full test suite to verify GREEN**

```
pytest tests/test_capture_skill.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add skills/capture/SKILL.md
git commit -m "feat: capture skill SKILL.md — on-demand + session-end modes, approval gate"
```

---

### Task 4: Update ROADMAP.md and ACTIVE.md

**Files:**
- Modify: `ROADMAP.md`
- Modify: `.ai/ACTIVE.md`

- [ ] **Step 1: Get the current HEAD SHA**

```bash
git rev-parse HEAD
```

Copy this SHA — you will use it as `synced-at-commit` in ACTIVE.md.

- [ ] **Step 2: Update ROADMAP.md**

In `ROADMAP.md` under "Build phase", make two changes:

Change the capture row from:
```
| ⏭️ | `capture` skill v0 | Writes a project-wiki page from a session. Plan 2 of 3. |
```
to:
```
| ✅ | `capture` skill v0 | `skills/capture/SKILL.md` + `REFERENCE.md`. Two-mode: on-demand + session-end. Approval gate. 2026-05-10. |
```

Change the sync row from:
```
| ☐ | `sync` skill v0 | Staleness detection via `synced-at-commit` + `describes-files`. Plan 3 of 3. |
```
to:
```
| ⏭️ | `sync` skill v0 | Staleness detection via `synced-at-commit` + `describes-files`. Plan 3 of 3. |
```

- [ ] **Step 3: Replace .ai/ACTIVE.md**

Replace the full contents of `.ai/ACTIVE.md` with (substituting the real SHA from Step 1):

```markdown
---
id: memex:wiki:active
slug: active
title: Memex — current focus
synced-at-commit: <HEAD-SHA-FROM-STEP-1>
describes-files: ["ROADMAP.md", "GOALS.md"]
status: draft
tags: [product, active]
created: 2026-05-09
updated: 2026-05-10
---

# Current focus

**Capture skill v0 complete 2026-05-10.** `skills/capture/SKILL.md` + `REFERENCE.md` shipped. Two-mode: on-demand + session-end. Approval gate before every write. 4 tests passing. Next session is the `sync` skill v0.

## Next

1. **`sync` skill v0** — staleness detection via `synced-at-commit` + `describes-files`. Plan 3 of 3. Brainstorm → plan → implement. Inputs: `docs/WIKI_PAGE_FORMAT.md`, `db/schema.sql`, `scripts/rebuild.py`.

2. **`docs/MEMEX_SPEC.md`** — short spec of what Memex is, does, and doesn't do. Can be written in parallel with sync or just before v0.1 release.

## Completed

- Format & schema lock — 2026-05-09
- Rebuild script — 2026-05-09 (13 tests, CLI, smoke tested)
- Capture skill v0 — 2026-05-10 (SKILL.md + REFERENCE.md, 4 tests)

## Open items

- `docs/MEMEX_SPEC.md` not yet written
- 3 quality follow-ups from rebuild code review (non-blocking): surface dropped links as warnings; friendlier error on duplicate id; decide policy for created/updated defaults

## Pointer

If this entry is stale, compare `synced-at-commit` to repo HEAD; check whether `describes-files` have changed.
```

- [ ] **Step 4: Commit**

```bash
git add ROADMAP.md .ai/ACTIVE.md
git commit -m "chore: mark capture skill v0 done; advance sync to next"
```

---

## Self-review checklist

- [ ] All tasks produce working, committable content on their own ✓
- [ ] No TBDs or placeholders in SKILL.md or REFERENCE.md ✓
- [ ] SKILL.md content above is 79 lines — ≤100 ✓
- [ ] Description above is ~368 chars — ≤1024 ✓
- [ ] Task 1 tests fail (RED) before Task 3 and pass (GREEN) after Task 3 ✓
- [ ] `parse_page()` and `rebuild()` imports match exports in `scripts/rebuild.py` ✓
- [ ] `frontmatter` import in test is the python-frontmatter package already in `scripts/requirements.txt` ✓
- [ ] Fixture page has all five required frontmatter fields (`id`, `title`, `status`, `created`, `updated`) ✓
- [ ] ACTIVE.md `synced-at-commit` placeholder is flagged in Step 3 with explicit instruction to substitute real SHA ✓
- [ ] Commit messages follow `feat:` / `test:` / `chore:` convention ✓
