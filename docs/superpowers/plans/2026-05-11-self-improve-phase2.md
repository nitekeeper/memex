# Self-Improve Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `self-improve` skill with solo and collaborative modes, and update `review-lessons` to surface held items first.

**Architecture:** Two tasks in sequence. Task 1 creates the new `self-improve` skill with its REFERENCE.md, tests, and a held-item fixture. Task 2 updates `review-lessons` to scan held items first and show `[HELD]` markers, with a new fixture and additional tests.

**Tech Stack:** Markdown (SKILL.md, REFERENCE.md), Python + pytest + python-frontmatter (tests)

---

## File structure

| File | Action | Purpose |
|---|---|---|
| `skills/self-improve/SKILL.md` | Create | Solo + collaborative mode instructions |
| `skills/self-improve/REFERENCE.md` | Create | Held-item format, commit messages, error handling |
| `tests/test_self_improve_skill.py` | Create | Structural + fixture tests for self-improve |
| `tests/fixtures/self-improve-output/lessons/inbox/test-held.md` | Create | Held-item fixture for self-improve tests |
| `skills/review-lessons/SKILL.md` | Modify | Add held-first scan order + [HELD] markers |
| `tests/test_review_lessons_skill.py` | Modify | Add held-item fixture test |
| `tests/fixtures/review-lessons-output/lessons/inbox/test-held.md` | Create | Held-item fixture for review-lessons tests |

---

### Task 1: Create self-improve skill

**Files:**
- Create: `skills/self-improve/SKILL.md`
- Create: `skills/self-improve/REFERENCE.md`
- Create: `tests/fixtures/self-improve-output/lessons/inbox/test-held.md`
- Create: `tests/test_self_improve_skill.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_self_improve_skill.py`:

```python
import pathlib
import frontmatter as fm

SKILL_MD = pathlib.Path(__file__).parent.parent / "skills" / "self-improve" / "SKILL.md"
REFERENCE_MD = pathlib.Path(__file__).parent.parent / "skills" / "self-improve" / "REFERENCE.md"
FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures" / "self-improve-output"
HELD_LESSON = FIXTURES_DIR / "lessons" / "inbox" / "test-held.md"


def test_skill_md_exists():
    """skills/self-improve/SKILL.md must exist."""
    assert SKILL_MD.exists(), "skills/self-improve/SKILL.md must exist"


def test_skill_md_under_150_lines():
    """SKILL.md must stay ≤150 lines."""
    assert SKILL_MD.exists(), "skills/self-improve/SKILL.md must exist"
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
    """skills/self-improve/REFERENCE.md must exist."""
    assert REFERENCE_MD.exists(), "skills/self-improve/REFERENCE.md must exist"


def test_held_lesson_fixture_parses():
    """Held fixture must parse with held-for-review=true and valid held-reason."""
    post = fm.load(str(HELD_LESSON))
    assert post.metadata.get("held-for-review") is True, "held-for-review must be true"
    valid = {"contradiction", "philosophy", "confidence"}
    assert post.metadata.get("held-reason") in valid, \
        f"held-reason must be one of {valid}, got {post.metadata.get('held-reason')!r}"


def test_held_lesson_is_draft():
    """Held fixture must have status: draft."""
    post = fm.load(str(HELD_LESSON))
    assert post.metadata.get("status") == "draft", "held lesson must have status: draft"


def test_held_lesson_has_required_fields():
    """Held fixture must have all required lesson fields."""
    post = fm.load(str(HELD_LESSON))
    for field in ["id", "title", "stream", "status", "created"]:
        assert field in post.metadata, f"Missing required field: {field}"


def test_held_lesson_id_format():
    """id must follow <project>:lesson:<slug>."""
    post = fm.load(str(HELD_LESSON))
    parts = post.metadata["id"].split(":")
    assert len(parts) == 3, f"id must be <project>:lesson:<slug>, got {post.metadata['id']}"
    assert parts[1] == "lesson", f"id type must be 'lesson', got {parts[1]}"


def test_held_lesson_body_has_required_sections():
    """Held lesson body must have all three required sections."""
    post = fm.load(str(HELD_LESSON))
    assert "## Observation" in post.content
    assert "## Why it matters" in post.content
    assert "## How to apply" in post.content
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:\Users\user\Documents\Skills\memex
python -m pytest tests/test_self_improve_skill.py -v
```

Expected: all 9 tests FAIL (files don't exist yet).

- [ ] **Step 3: Create the held-item fixture**

Create directory `tests/fixtures/self-improve-output/lessons/inbox/` and write `test-held.md`:

```markdown
---
id: memex:lesson:test-held-philosophy
title: Test held lesson — philosophy signal
stream: inbox
status: draft
tags: [test-artifact]
created: 2026-05-11
held-for-review: true
held-reason: philosophy
---

## Observation

This is a test fixture for the self-improve skill's held-item filter. It was held because it touches design philosophy — specifically, a value judgment about wiki curation priorities that requires human review rather than autonomous promotion.

## Why it matters

Lessons touching goals, priorities, design direction, or methodology require human judgment. The solo filter holds these rather than promoting them silently.

## How to apply

When reviewing held lessons with `held-reason: philosophy`, check whether the value judgment aligns with current project goals before deciding to promote or discard.
```

- [ ] **Step 4: Create `skills/self-improve/SKILL.md`**

```markdown
---
description: "Use when the user wants to run the self-improvement loop — either solo (Claude runs it autonomously without gates) or collaboratively (user and Claude work through it together with approval at each step). Trigger on: \"self-improve\", \"run self-improve\", \"self-improvement loop\", \"run the loop solo\", \"let's do self-improve together\", \"self-improve on your own\", \"review our lessons together\". Also trigger when the user asks Claude to capture and review lessons as a batch in one invocation."
---

# self-improve — run the self-improvement loop

## Mode detection

Detect mode from invocation phrasing:
- **Solo** — "run self-improve solo", "self-improve on your own", "do it yourself", or similar autonomous framing.
- **Collaborative** — "let's run self-improve", "self-improve together", "run self-improve with me", or similar joint framing.

If phrasing is ambiguous, ask: "Solo (I run it autonomously) or collaborative (we work through it together)?"

After detecting mode, confirm the target project root: a project is detectable if it contains `lessons/inbox/` at its root. Zero projects → stop with instructions. One project → proceed. Multiple → ask user to choose.

---

## Solo mode

Runs the full pipeline without approval gates.

### Step 1 — Capture

Sweep the current conversation for lesson candidates (same logic as `capture-lesson` session-end mode):
- Non-obvious observations, mid-session corrections, decisions with a "why", patterns that help a future AI avoid a mistake
- Skip: task-local notes, obvious-from-code items, ephemeral state, any slug already in `lessons/` or `.ai/wiki/`
- If no active conversation: tell the user "Solo mode requires an active conversation to sweep for lessons." Stop.

### Step 2 — Filter

Evaluate each candidate against three signals. Any one triggers a hold:

| Signal | Condition |
|---|---|
| Contradiction | Conflicts with an existing `status: approved` wiki entry in `.ai/wiki/` |
| Philosophy/goals | Touches goals, priorities, design direction, or methodology |
| Low confidence | Would naturally be phrased as "I think", "it seems", or "possibly" |

- **Confident candidates** → write to `lessons/inbox/<slug>.md` as `status: draft`
- **Held candidates** → write to `lessons/inbox/<slug>.md` as `status: draft` plus `held-for-review: true` and `held-reason: contradiction | philosophy | confidence` (see REFERENCE.md for format)

### Step 3 — Review + propose (solo, no gates)

Run `review-lessons` solo on confident lessons only (skip held items). Apply promote/defer/discard heuristics directly. Then run `propose-wiki-entry` solo on any promoted lessons.

### Step 4 — Summary + commit

Show summary (see REFERENCE.md for format). Commit: `chore: self-improve solo run — YYYY-MM-DD`. Skip commit if no file changes.

---

## Collaborative mode

### Step 1 — Mode selection

Ask:
```
Self-improve — collaborative mode.
What would you like to do?
a) Full loop — capture new lessons from this conversation, then review everything together
b) Queue review — review held items and existing drafts (no fresh capture)
```

### Step 2 — Execute

**Option a — Full loop:**
1. Run `capture-lesson` (session-end mode, with gates)
2. Run `review-lessons` (with gates — held items surface first)
3. Run `propose-wiki-entry` (with gates)

**Option b — Queue review:**
1. Run `review-lessons` (with gates — held items surface first)
2. Run `propose-wiki-entry` (with gates)

Each skill runs its own approval gates. Nothing is written without user confirmation.
```

- [ ] **Step 5: Create `skills/self-improve/REFERENCE.md`**

```markdown
# self-improve — Reference

## Held-item frontmatter

When a lesson is held by the solo filter, add these fields to its frontmatter:

| Field | Type | Values |
|---|---|---|
| `held-for-review` | boolean | Always `true` |
| `held-reason` | string | `contradiction`, `philosophy`, or `confidence` |

Example:
```yaml
---
id: memex:lesson:auth-tradeoffs
title: Auth design tradeoffs require human judgment
stream: inbox
status: draft
tags: [auth, design]
created: 2026-05-11
held-for-review: true
held-reason: philosophy
---
```

## Solo mode summary format

```
Self-improve solo run — YYYY-MM-DD
  Captured: N candidates
    Written: X
    Held for collaborative review: Y
      - <title> (reason: contradiction with <wiki-slug>)
      - <title> (reason: philosophy/goals)
      - <title> (reason: low confidence)
  Wiki entries proposed: M
```

If no candidates found: `Self-improve solo run — nothing to capture. Ready.`

## Commit message format

| Event | Message |
|---|---|
| Solo run with changes | `chore: self-improve solo run — YYYY-MM-DD` |
| Solo run, no changes | skip commit |

Em dash: use literal `—` (U+2014), not `--`.

## Error handling

| Situation | Action |
|---|---|
| Solo mode, no active conversation | Tell user: 'Solo mode requires an active conversation. Start a session first.' Stop. |
| No detectable project | Tell user: 'No lessons directory found. Create `lessons/inbox/` in your project root.' Stop. |
| Multiple detectable projects | Ask user which project. Wait for explicit choice. |
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd C:\Users\user\Documents\Skills\memex
python -m pytest tests/test_self_improve_skill.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 7: Run full suite to check for regressions**

```bash
python -m pytest tests/ -v
```

Expected: all tests PASS (72 existing + 9 new = 81 total).

- [ ] **Step 8: Commit**

```bash
git add skills/self-improve/ tests/test_self_improve_skill.py tests/fixtures/self-improve-output/
git commit -m "feat: add self-improve skill v0 — solo + collaborative modes"
```

---

### Task 2: Update review-lessons for held items

**Files:**
- Modify: `skills/review-lessons/SKILL.md`
- Create: `tests/fixtures/review-lessons-output/lessons/inbox/test-held.md`
- Modify: `tests/test_review_lessons_skill.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_review_lessons_skill.py`:

```python
HELD_LESSON = FIXTURES_DIR / "lessons" / "inbox" / "test-held.md"


def test_held_lesson_fixture_parses():
    """Held fixture must parse with held-for-review=true and valid held-reason."""
    post = fm.load(str(HELD_LESSON))
    assert post.metadata.get("held-for-review") is True, "held-for-review must be true"
    valid = {"contradiction", "philosophy", "confidence"}
    assert post.metadata.get("held-reason") in valid, \
        f"held-reason must be one of {valid}"
    assert post.metadata.get("status") == "draft"
```

Add `HELD_LESSON` definition after the existing fixture path definitions at the top of the file (after `DISCARDED_LESSON`):

```python
HELD_LESSON = FIXTURES_DIR / "lessons" / "inbox" / "test-held.md"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd C:\Users\user\Documents\Skills\memex
python -m pytest tests/test_review_lessons_skill.py::test_held_lesson_fixture_parses -v
```

Expected: FAIL — fixture file does not exist yet.

- [ ] **Step 3: Create the held-item fixture**

Create `tests/fixtures/review-lessons-output/lessons/inbox/test-held.md`:

```markdown
---
id: memex:lesson:test-held-review-lessons
title: Test held lesson — for review-lessons held-item surfacing
stream: inbox
status: draft
tags: [test-artifact]
created: 2026-05-11
held-for-review: true
held-reason: contradiction
---

## Observation

This is a test fixture for the review-lessons held-item scan order. It was held because it contradicts an existing approved wiki entry. It should surface before regular draft lessons in the candidate list.

## Why it matters

Held items require collaborative human review. Surfacing them first ensures they are not overlooked when the user runs review-lessons after a solo self-improve pass.

## How to apply

When reviewing held lessons with `held-reason: contradiction`, identify which wiki entry the lesson conflicts with and decide whether to update the wiki entry, discard the lesson, or promote the lesson and archive the wiki entry.
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_review_lessons_skill.py::test_held_lesson_fixture_parses -v
```

Expected: PASS.

- [ ] **Step 5: Update `skills/review-lessons/SKILL.md`**

Read the current file first. Then make three targeted changes:

**Change 1 — Scan step:** Replace the current Step 1 scan block:

```markdown
1. **Scan** for draft lessons:
   - Read all `.md` files in `lessons/feedback/` and `lessons/inbox/` with `status: draft`
   - Feedback stream first (higher priority), then inbox
   - Skip files with `status` not `draft`
```

With:

```markdown
1. **Scan** for draft lessons:
   - Read all `.md` files in `lessons/feedback/` and `lessons/inbox/` with `status: draft`
   - Skip files with `status` not `draft`
   - Bucket into two groups:
     - **Held**: files with `held-for-review: true` (feedback stream first, then inbox)
     - **Regular**: all other draft files (feedback stream first, then inbox)
   - Review order: held items first, then regular drafts
```

**Change 2 — Candidate list:** Replace the candidate list format:

```markdown
   Found N draft lessons (F feedback, I inbox):
   1. <title> (feedback)
   2. <title> (inbox)
   Proceed? (yes / cancel)
```

With:

```markdown
   Found N draft lessons (H held, F feedback, I inbox):
   1. <title> (feedback) [HELD: philosophy]
   2. <title> (inbox) [HELD: contradiction]
   3. <title> (feedback)
   4. <title> (inbox)
   Proceed? (yes / cancel)
```

(Only show `[HELD: <reason>]` for held items. Omit for regular drafts. Omit `H held` count from header if H is 0.)

**Change 3 — Review block:** Add held-item variant. After the existing review block:

```markdown
   ```
   --- Lesson <n> of N ---
   Title: <title>
   Stream: <stream>  |  Tags: [...]
   
   How to apply: <how-to-apply content>
   
   Action? (promote / discard / defer)
   ```
```

Add:

```markdown
   For held items, prepend the held marker and reason:
   ```
   --- Lesson <n> of N --- [HELD: <reason>]
   Title: <title>
   Stream: <stream>  |  Tags: [...]

   Held reason: <contradiction with <wiki-slug> | touches philosophy/goals | low confidence>
   How to apply: <how-to-apply content>

   Action? (promote / discard / defer)
   ```
   When a held lesson is promoted, also clear `held-for-review` and `held-reason` from its frontmatter before writing.
```

- [ ] **Step 6: Run full test suite**

```bash
cd C:\Users\user\Documents\Skills\memex
python -m pytest tests/ -v
```

Expected: all tests PASS. The `test_skill_md_under_150_lines` test for review-lessons must still pass — check that the updated SKILL.md is ≤150 lines.

If `test_skill_md_under_150_lines` fails (file now exceeds 150 lines): trim prose in the review block description to stay under the limit without removing behavioral content.

- [ ] **Step 7: Commit**

```bash
git add skills/review-lessons/SKILL.md tests/test_review_lessons_skill.py tests/fixtures/review-lessons-output/lessons/inbox/test-held.md
git commit -m "feat: update review-lessons — held-first scan order and [HELD] markers"
```
