# Memex `sync` Skill v0 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `sync` skill — a Python detection script plus an AI procedure file that surfaces stale project-wiki pages and walks the user through reviewing and stamping them as current.

**Architecture:** `scripts/sync.py` walks `.ai/wiki/`, reads frontmatter, runs `git diff` per page, and outputs a JSON staleness report. `skills/sync/SKILL.md` reads the report and handles the human-facing review and approval workflow. `skills/sync/REFERENCE.md` holds the stamp procedure, git command reference, and commit format. One addition to `skills/capture/SKILL.md`: a one-line post-write reminder when a code-tracking page is written.

**Tech Stack:** Python 3.11+ · python-frontmatter 1.1.0 · pytest 8.x · subprocess (real git calls in tests, no mocking)

---

## Scope note

This is Plan 3 of 3 for the Memex build phase. Plans 1 (rebuild script) and 2 (capture skill) are complete.

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `scripts/sync.py` | Create | Walk `.ai/wiki/`, detect staleness via `git diff`, output JSON report |
| `skills/sync/SKILL.md` | Create | AI procedure: read report, fast-forward or guided-edit per page, batch commit |
| `skills/sync/REFERENCE.md` | Create | Stamp procedure, git commands, assessment rule, commit format |
| `tests/test_sync_script.py` | Create | 8 tests: staleness detection (real git), SKILL.md constraints, error exits |
| `skills/capture/SKILL.md` | Modify | Add one-line post-write reminder to on-demand step 6 |
| `ROADMAP.md` | Modify | Mark sync skill v0 ✅; advance to self-improvement loop |
| `.ai/ACTIVE.md` | Modify | Point to next milestone |

---

### Task 1: Write tests (RED state)

Write all 8 tests before touching any implementation. Tests must fail predictably.

**Files:**
- Create: `tests/test_sync_script.py`

- [ ] **Step 1: Create `tests/test_sync_script.py`**

```python
import json
import pathlib
import subprocess
import sys

import frontmatter as fm
import pytest

SYNC_SCRIPT = str(pathlib.Path(__file__).parent.parent / "scripts" / "sync.py")
SKILL_MD = str(pathlib.Path(__file__).parent.parent / "skills" / "sync" / "SKILL.md")


def _git(args, cwd):
    return subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True, check=True
    )


def _run_sync(ai_dir):
    return subprocess.run(
        [sys.executable, SYNC_SCRIPT, str(ai_dir)],
        capture_output=True,
        text=True,
    )


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    ai_dir = repo / ".ai"
    wiki_dir = ai_dir / "wiki"
    wiki_dir.mkdir(parents=True)
    _git(["init"], cwd=repo)
    _git(["config", "user.email", "test@example.com"], cwd=repo)
    _git(["config", "user.name", "Test"], cwd=repo)
    return repo, ai_dir, wiki_dir


def test_stale_page_detected(git_repo):
    repo, ai_dir, wiki_dir = git_repo
    tracked = repo / "db" / "schema.sql"
    tracked.parent.mkdir()
    tracked.write_text("CREATE TABLE foo (id INTEGER);")
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "initial"], cwd=repo)
    sha_a = _git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()

    page = wiki_dir / "db-schema.md"
    page.write_text(
        f"---\n"
        f"id: test:wiki:db-schema\n"
        f"title: DB Schema\n"
        f"status: draft\n"
        f"created: 2026-05-10\n"
        f"updated: 2026-05-10\n"
        f"describes-files:\n"
        f"  - db/schema.sql\n"
        f"synced-at-commit: {sha_a}\n"
        f"---\n\n"
        f"Describes the database schema.\n"
    )
    tracked.write_text(
        "CREATE TABLE foo (id INTEGER);\nCREATE TABLE bar (id INTEGER);"
    )
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "add page and modify schema"], cwd=repo)

    result = _run_sync(ai_dir)
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert len(report["stale"]) == 1
    assert report["stale"][0]["state"] == "STALE"
    assert report["stale"][0]["id"] == "test:wiki:db-schema"
    assert len(report["stale"][0]["changed_files"]) == 1
    assert report["stale"][0]["changed_files"][0]["diff"] is not None
    assert report["stale"][0]["changed_files"][0]["lines_changed"] > 0


def test_never_synced_page_detected(git_repo):
    repo, ai_dir, wiki_dir = git_repo
    tracked = repo / "src" / "auth.py"
    tracked.parent.mkdir()
    tracked.write_text("def auth(): pass")
    page = wiki_dir / "auth-flow.md"
    page.write_text(
        "---\n"
        "id: test:wiki:auth-flow\n"
        "title: Auth Flow\n"
        "status: draft\n"
        "created: 2026-05-10\n"
        "updated: 2026-05-10\n"
        "describes-files:\n"
        "  - src/auth.py\n"
        "---\n\n"
        "Describes the auth flow.\n"
    )
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "initial"], cwd=repo)

    result = _run_sync(ai_dir)
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert len(report["stale"]) == 1
    assert report["stale"][0]["state"] == "NEVER_SYNCED"
    assert report["stale"][0]["synced_at_commit"] is None
    assert report["stale"][0]["changed_files"][0]["diff"] is None
    assert report["stale"][0]["changed_files"][0]["lines_changed"] is None


def test_clean_page_not_stale(git_repo):
    repo, ai_dir, wiki_dir = git_repo
    tracked = repo / "db" / "schema.sql"
    tracked.parent.mkdir()
    tracked.write_text("CREATE TABLE foo (id INTEGER);")
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "initial"], cwd=repo)
    sha_a = _git(["rev-parse", "HEAD"], cwd=repo).stdout.strip()

    page = wiki_dir / "db-schema.md"
    page.write_text(
        f"---\n"
        f"id: test:wiki:db-schema\n"
        f"title: DB Schema\n"
        f"status: draft\n"
        f"created: 2026-05-10\n"
        f"updated: 2026-05-10\n"
        f"describes-files:\n"
        f"  - db/schema.sql\n"
        f"synced-at-commit: {sha_a}\n"
        f"---\n\n"
        f"Describes the database schema.\n"
    )
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "add wiki page"], cwd=repo)

    result = _run_sync(ai_dir)
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert len(report["stale"]) == 0
    assert len(report["clean"]) == 1
    assert report["clean"][0]["state"] == "CLEAN"
    assert report["clean"][0]["id"] == "test:wiki:db-schema"


def test_untracked_page_ignored(git_repo):
    repo, ai_dir, wiki_dir = git_repo
    page = wiki_dir / "concept.md"
    page.write_text(
        "---\n"
        "id: test:wiki:concept\n"
        "title: A Concept\n"
        "status: draft\n"
        "created: 2026-05-10\n"
        "updated: 2026-05-10\n"
        "---\n\n"
        "A concept page with no file tracking.\n"
    )
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "initial"], cwd=repo)

    result = _run_sync(ai_dir)
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert len(report["stale"]) == 0
    assert len(report["clean"]) == 0
    assert len(report["untracked"]) == 1
    assert report["untracked"][0]["id"] == "test:wiki:concept"


def test_bad_ai_dir_exits_nonzero(tmp_path):
    result = _run_sync(tmp_path / "nonexistent" / ".ai")
    assert result.returncode != 0


def test_unresolvable_sha_exits_nonzero(git_repo):
    repo, ai_dir, wiki_dir = git_repo
    tracked = repo / "db" / "schema.sql"
    tracked.parent.mkdir()
    tracked.write_text("CREATE TABLE foo (id INTEGER);")
    page = wiki_dir / "db-schema.md"
    page.write_text(
        "---\n"
        "id: test:wiki:db-schema\n"
        "title: DB Schema\n"
        "status: draft\n"
        "created: 2026-05-10\n"
        "updated: 2026-05-10\n"
        "describes-files:\n"
        "  - db/schema.sql\n"
        "synced-at-commit: deadbeefdeadbeefdeadbeef\n"
        "---\n\n"
        "Describes the database schema.\n"
    )
    _git(["add", "."], cwd=repo)
    _git(["commit", "-m", "initial"], cwd=repo)

    result = _run_sync(ai_dir)
    assert result.returncode != 0
    assert "deadbeefdeadbeefdeadbeef" in result.stderr


def test_skill_md_under_100_lines():
    with open(SKILL_MD, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) <= 100, f"SKILL.md is {len(lines)} lines — must be ≤100"


def test_skill_description_under_1024_chars():
    post = fm.load(SKILL_MD)
    desc = str(post.metadata.get("description", ""))
    assert len(desc) > 0, "description field is empty"
    assert len(desc) <= 1024, f"description is {len(desc)} chars — must be ≤1024"
```

- [ ] **Step 2: Run tests to confirm RED state**

Run from the Memex repo root:
```
pytest tests/test_sync_script.py -v
```

Expected:
- `test_stale_page_detected` — FAIL (`FileNotFoundError`: sync.py missing)
- `test_never_synced_page_detected` — FAIL
- `test_clean_page_not_stale` — FAIL
- `test_untracked_page_ignored` — FAIL
- `test_bad_ai_dir_exits_nonzero` — FAIL
- `test_unresolvable_sha_exits_nonzero` — FAIL
- `test_skill_md_under_100_lines` — FAIL (`FileNotFoundError`: SKILL.md missing)
- `test_skill_description_under_1024_chars` — FAIL

- [ ] **Step 3: Commit**

```
git add tests/test_sync_script.py
git commit -m "test: sync skill tests — staleness detection, constraints, error exits"
```

---

### Task 2: Implement `scripts/sync.py`

**Files:**
- Create: `scripts/sync.py`

- [ ] **Step 1: Create `scripts/sync.py`**

```python
import json
import os
import pathlib
import subprocess
import sys

import frontmatter


def _git(args, cwd, check=True):
    return subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True, check=check
    )


def _get_head_sha(project_root):
    return _git(["rev-parse", "HEAD"], cwd=project_root).stdout.strip()


def _validate_sha(project_root, sha):
    result = _git(["cat-file", "-t", sha], cwd=project_root, check=False)
    return result.returncode == 0


def _get_file_diff(project_root, sha, file_path):
    result = _git(
        ["diff", f"{sha}..HEAD", "--", file_path], cwd=project_root
    )
    return result.stdout


def _count_lines_changed(diff_text):
    added = sum(
        1 for line in diff_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    removed = sum(
        1 for line in diff_text.splitlines()
        if line.startswith("-") and not line.startswith("---")
    )
    return added + removed


def run_sync(ai_dir):
    ai_path = pathlib.Path(ai_dir)
    if not ai_path.exists():
        print(f"Error: ai_dir not found: {ai_dir}", file=sys.stderr)
        sys.exit(1)

    project_root = str(ai_path.parent)

    try:
        head_sha = _get_head_sha(project_root)
    except subprocess.CalledProcessError as exc:
        print(f"Error: git unavailable or not a git repo: {exc}", file=sys.stderr)
        sys.exit(1)

    report = {"head": head_sha, "stale": [], "clean": [], "untracked": []}

    wiki_dir = ai_path / "wiki"
    if not wiki_dir.exists():
        print(json.dumps(report, indent=2))
        return

    for md_file in sorted(wiki_dir.glob("*.md")):
        post = frontmatter.load(str(md_file))
        meta = post.metadata
        page_id = str(meta.get("id", ""))
        title = str(meta.get("title", ""))
        page_path = str(md_file.relative_to(ai_path.parent)).replace("\\", "/")
        describes_files = list(meta.get("describes-files", []))
        synced_at_commit = meta.get("synced-at-commit")

        if not describes_files:
            report["untracked"].append(
                {"page": page_path, "id": page_id, "title": title}
            )
            continue

        if not synced_at_commit:
            report["stale"].append(
                {
                    "page": page_path,
                    "id": page_id,
                    "title": title,
                    "state": "NEVER_SYNCED",
                    "synced_at_commit": None,
                    "changed_files": [
                        {"path": fp, "diff": None, "lines_changed": None}
                        for fp in describes_files
                    ],
                }
            )
            continue

        if not _validate_sha(project_root, synced_at_commit):
            print(
                f"Error: synced-at-commit '{synced_at_commit}' in {md_file} "
                f"is not a valid git object",
                file=sys.stderr,
            )
            sys.exit(1)

        changed_files = []
        for fp in describes_files:
            diff_text = _get_file_diff(project_root, synced_at_commit, fp)
            if diff_text:
                changed_files.append(
                    {
                        "path": fp,
                        "diff": diff_text,
                        "lines_changed": _count_lines_changed(diff_text),
                    }
                )

        if changed_files:
            report["stale"].append(
                {
                    "page": page_path,
                    "id": page_id,
                    "title": title,
                    "state": "STALE",
                    "synced_at_commit": synced_at_commit,
                    "changed_files": changed_files,
                }
            )
        else:
            report["clean"].append(
                {
                    "page": page_path,
                    "id": page_id,
                    "title": title,
                    "state": "CLEAN",
                    "synced_at_commit": synced_at_commit,
                    "changed_files": [],
                }
            )

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Detect stale Memex wiki pages via git diff."
    )
    parser.add_argument("ai_dir", help="Path to the project's .ai/ directory")
    args = parser.parse_args()
    run_sync(args.ai_dir)
```

- [ ] **Step 2: Run the 6 script tests to verify GREEN (SKILL.md tests still RED)**

```
pytest tests/test_sync_script.py -v -k "not skill_md"
```

Expected: 6 PASS (`test_stale_page_detected`, `test_never_synced_page_detected`, `test_clean_page_not_stale`, `test_untracked_page_ignored`, `test_bad_ai_dir_exits_nonzero`, `test_unresolvable_sha_exits_nonzero`)

- [ ] **Step 3: Commit**

```
git add scripts/sync.py
git commit -m "feat: sync.py — staleness detection script with JSON report output"
```

---

### Task 3: Write `skills/sync/REFERENCE.md`

**Files:**
- Create: `skills/sync/REFERENCE.md`

- [ ] **Step 1: Create `skills/sync/REFERENCE.md`**

```markdown
# sync — Reference

## Stamp procedure

When stamping a page (fast-forward or after conflict-gate approval):
1. Read the file at the page path.
2. Update `synced-at-commit` to the HEAD SHA (use the `head` field from the JSON report).
3. Update `updated` to today's date (YYYY-MM-DD — read from session context `# currentDate` if present; otherwise run `Get-Date -Format yyyy-MM-dd` on Windows or `date +%Y-%m-%d` on POSIX).
4. Write the file back. Do not change any other field.
5. Do not run `rebuild.py` — the sync skill manages only `synced-at-commit` and `updated`.

## Git commands used by `sync.py`

| Purpose | Command |
|---|---|
| Get HEAD SHA | `git rev-parse HEAD` |
| Validate a SHA exists | `git cat-file -t <sha>` |
| Get diff for a file | `git diff <sha>..HEAD -- <file>` |

## Assessment rule

**Default conservative: if in doubt, treat as conflict.**

**Fast-forward** — diff is purely cosmetic: whitespace normalization, comment rewording, or file moves with no semantic change. The page content remains fully accurate after the change.

**Conflict** — any structural or semantic change to a tracked file, any new information not yet reflected in the page, or any doubt about accuracy. The cost of a false conflict is one extra approval. The cost of a false fast-forward is silently stale wiki content.

## Page states (from `sync.py` JSON output)

| State | Meaning |
|---|---|
| `STALE` | `describes-files` set + `synced-at-commit` set; files changed since that commit |
| `NEVER_SYNCED` | `describes-files` set; `synced-at-commit` absent or null |
| `CLEAN` | `describes-files` set + `synced-at-commit` set; no files changed since that commit |
| `UNTRACKED` | No `describes-files`; concept/decision page; not evaluated by sync |

## Commit message format

`wiki: sync — N pages`

N is the count of pages stamped (fast-forward + conflict-approved combined).

> **Em dash encoding check:** Before committing, run `git config i18n.commitEncoding`. If the command exits with code 0 and output is empty, `utf-8`, `utf8`, `UTF-8`, or `UTF8` — use the Unicode em dash (U+2014, `—`). Otherwise substitute `--` (ASCII double-hyphen). If `git commit` fails for any reason, show the git error and do not retry.
```

- [ ] **Step 2: Commit**

```
git add skills/sync/REFERENCE.md
git commit -m "feat: sync skill REFERENCE.md — stamp procedure, assessment rule, commit format"
```

---

### Task 4: Write `skills/sync/SKILL.md` (all tests GREEN)

**Files:**
- Create: `skills/sync/SKILL.md`

- [ ] **Step 1: Create `skills/sync/SKILL.md`**

```markdown
---
description: "Use when the user wants to check whether project-wiki pages that track source files are still accurate, or to review and update stale pages. Also use when the user invokes /sync. Do NOT use for writing new pages (use capture) or ingesting external sources (use meta:ingest-source)."
---

# sync — detect and review stale wiki pages

## Project root detection

Check each workspace root for `.ai/wiki/`. Zero → stop: 'No project wiki found. Create an `.ai/wiki/` directory in your target project root before running sync.' One → proceed, announce: 'Syncing `<absolute-path>/.ai/wiki/`.' Many → ask user to choose. Do not infer from recency or context.

## Explicit mode (`/sync`)

1. **Run** `python scripts/sync.py .ai/` from the confirmed project root.
   On error: show stderr, stop.

2. **No stale pages:** report `All N tracked pages are current.` Done.

3. **For each stale or never-synced page** (one at a time, in report order):

   a. Read the current page content.
   b. `STALE`: read `changed_files[].diff` from the JSON report.
      `NEVER_SYNCED`: `diff` is null — read each `describes-files` path directly from disk.
   c. **Assess** — is the page content still accurate given the changes?
      - **Fast-forward** (diff is purely cosmetic — whitespace, comments, or formatting only — OR you are fully confident the page reflects all changes): stamp `synced-at-commit` to HEAD and `updated` to today. Announce: `Auto-synced: <title> — no content changes needed`. Continue.
      - **Conflict** (any doubt): show guided edit gate:
        ```
        Page: .ai/wiki/<slug>.md  [STALE since <sha>]  or  [NEVER SYNCED]
        Changed: <file> (+N / -M)
        <diff excerpt or current file summary>
        Proposed update:
        <AI-drafted revision of page body>
        ~<N> lines
        Approve? (yes / edit / skip)
        ```
        **yes** — write updated page, stamp `synced-at-commit` to HEAD, set `updated` to today.
        **edit** — apply correction, re-show gate.
        **skip** — leave page unchanged, do not stamp. Continue.
        Any other message — treat as edit instruction, apply, re-show gate.

4. **Batch commit** after all pages are processed:
   At least one stamped: `wiki: sync — N pages` (em dash check — see `REFERENCE.md`). Stage only stamped pages individually — do not use broad staging commands.
   Nothing stamped: `No pages stamped — nothing to commit.`

## Error handling

| Situation | Action |
|---|---|
| `sync.py` exits non-zero | Show stderr, stop. Do not stamp or commit. |
| Page file missing at report path | Warn: `Page file not found: <path> — skipping.` Continue. |
| `git commit` fails | Show error, do not retry. Files remain on disk uncommitted. |
| No `.ai/wiki/` directory | Stop: 'No project wiki found. Create an `.ai/wiki/` directory first.' |

For the stamp procedure, assessment rule, and commit format, see `REFERENCE.md`.
```

- [ ] **Step 2: Run the full test suite — all 8 tests GREEN**

```
pytest tests/test_sync_script.py -v
```

Expected: 8 PASS

- [ ] **Step 3: Commit**

```
git add skills/sync/SKILL.md
git commit -m "feat: sync skill SKILL.md — staleness review workflow with fast-forward and guided edit"
```

---

### Task 5: Update `skills/capture/SKILL.md`

Add a one-line post-write reminder to on-demand step 6. This is the only change to the capture skill.

**Files:**
- Modify: `skills/capture/SKILL.md`

- [ ] **Step 1: Read the current step 6 line**

Find this line in `skills/capture/SKILL.md`:

```
6. **Auto-commit**: `wiki: capture <slug> — <title>` (apply the em dash encoding check and commit failure handling from `REFERENCE.md` → Commit message formats)
```

- [ ] **Step 2: Append the reminder sentence to step 6**

Replace that line with:

```
6. **Auto-commit**: `wiki: capture <slug> — <title>` (apply the em dash encoding check and commit failure handling from `REFERENCE.md` → Commit message formats). If `describes-files` is non-empty on the written page, note after the commit: *'This page tracks files — run `/sync` to initialize staleness tracking.'*
```

- [ ] **Step 3: Run the capture tests to confirm no regressions**

```
pytest tests/test_capture_skill.py -v
```

Expected: all capture tests PASS.

- [ ] **Step 4: Commit**

```
git add skills/capture/SKILL.md
git commit -m "feat: capture skill — add post-write reminder for code-tracking pages"
```

---

### Task 6: Update `ROADMAP.md` and `.ai/ACTIVE.md`

**Files:**
- Modify: `ROADMAP.md`
- Modify: `.ai/ACTIVE.md`

- [ ] **Step 1: Get the current HEAD SHA**

```
git rev-parse HEAD
```

Copy this SHA — you will use it as `synced-at-commit` in ACTIVE.md.

- [ ] **Step 2: Update `ROADMAP.md`**

In the Memex `ROADMAP.md`, change the sync row from:
```
| ⏭️ | `sync` skill v0 | Staleness detection via `synced-at-commit` + `describes-files` (Foundation principle 12). Deep interface; detection logic hidden. Plan 3 of 3. |
```
to:
```
| ✅ | `sync` skill v0 | `skills/sync/SKILL.md` + `REFERENCE.md` + `scripts/sync.py`. Staleness detection + guided review. Fast-forward auto-stamp + conflict gate. 8 tests passing. 2026-05-10. |
```

And change the self-improvement loop row from:
```
| ☐ | Self-improvement loop v0 | Lesson capture/review, wiki curation passes. |
```
to:
```
| ⏭️ | Self-improvement loop v0 | Lesson capture/review, wiki curation passes. |
```

- [ ] **Step 3: Replace `.ai/ACTIVE.md`** (substitute real SHA from Step 1)

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

**Sync skill v0 complete 2026-05-10.** `skills/sync/SKILL.md` + `REFERENCE.md` + `scripts/sync.py` shipped. Staleness detection via `git diff`. Fast-forward auto-stamp + conflict guided-edit gate. 8 tests passing.

## Next

1. **Self-improvement loop v0** — lesson capture/review + wiki curation passes. Closes the dogfood loop.

2. **`docs/MEMEX_SPEC.md`** — short product overview spec. Write before v0.1 release.

3. **v0.1 release** — `dist/` cut with manifest; git tag.

## Completed

- Format & schema lock — 2026-05-09
- Rebuild script — 2026-05-09 (13 tests, CLI, smoke tested)
- Capture skill v0 — 2026-05-10 (SKILL.md + REFERENCE.md, 17 tests)
- Sync skill v0 — 2026-05-10 (SKILL.md + REFERENCE.md + sync.py, 8 tests)

## Open items

- Self-improvement loop not yet built
- `docs/MEMEX_SPEC.md` not yet written
- 3 quality follow-ups from rebuild code review (non-blocking): surface dropped links as warnings; friendlier error on duplicate id; decide policy for created/updated defaults

## Pointer

If this entry is stale, compare `synced-at-commit` to repo HEAD; check whether `describes-files` have changed.
```

- [ ] **Step 4: Commit**

```
git add ROADMAP.md .ai/ACTIVE.md
git commit -m "chore: mark sync skill v0 done; advance self-improvement loop to next"
```

---

## Self-review checklist

- [ ] All 8 tests have full code — no placeholders ✓
- [ ] `git_repo` fixture configures `user.email` and `user.name` so commits succeed ✓
- [ ] `SKILL.md` content above is ~60 lines — ≤100 ✓
- [ ] SKILL.md description above is ~265 chars — ≤1024 ✓
- [ ] `sync.py` uses `sys.executable` in tests (not bare `python`) for cross-env compatibility ✓
- [ ] Page path uses forward slashes in JSON output (`.replace("\\", "/")`) for cross-platform consistency ✓
- [ ] `run_sync` in tests calls via subprocess, not import — matches real CLI invocation ✓
- [ ] Task 5 (capture edit) includes a regression test run ✓
- [ ] ACTIVE.md `synced-at-commit` placeholder is flagged with explicit substitution instruction ✓
- [ ] Commit messages follow `feat:` / `test:` / `chore:` convention ✓
