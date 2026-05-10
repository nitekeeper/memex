# capture-lesson Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `capture-lesson` skill — a pure LLM skill that writes lesson files from session observations into `lessons/inbox/` or `lessons/feedback/`.

**Architecture:** Three deliverables: `skills/capture-lesson/SKILL.md` (skill procedure), `skills/capture-lesson/REFERENCE.md` (format spec + routing rules), and `docs/LESSON_FORMAT.md` (standalone format doc). No script — pure LLM skill. Mirrors the `capture` skill's structure. Tests validate fixture output and structural invariants (line count, description length, required files present).

**Tech Stack:** Python 3, pytest, `python-frontmatter` (already in `requirements.txt`)

---

## File map

| Action | Path | Responsibility |
|---|---|---|
| Create | `tests/fixtures/capture-lesson-output/lessons/inbox/test-lesson.md` | Fixture: inbox lesson the skill would produce |
| Create | `tests/fixtures/capture-lesson-output/lessons/feedback/test-feedback.md` | Fixture: feedback lesson the skill would produce |
| Create | `tests/test_capture_lesson_skill.py` | 9 tests: fixture validity, structural invariants |
| Create | `docs/LESSON_FORMAT.md` | Standalone lesson format reference |
| Create | `skills/capture-lesson/REFERENCE.md` | Field rules, stream routing, commit format, error table |
| Create | `skills/capture-lesson/SKILL.md` | Skill procedure (≤150 lines) |

---

## Task 1: Fixtures and test file

**Files:**
- Create: `tests/fixtures/capture-lesson-output/lessons/inbox/test-lesson.md`
- Create: `tests/fixtures/capture-lesson-output/lessons/feedback/test-feedback.md`
- Create: `tests/test_capture_lesson_skill.py`

- [ ] **Step 1: Create the inbox fixture**

Create `tests/fixtures/capture-lesson-output/lessons/inbox/test-lesson.md`:

```markdown
---
id: memex:lesson:test-lesson
title: Approval gate must appear before any file write
stream: inbox
status: draft
tags: [test, approval-gate]
created: 2026-05-10
---

## Observation

When implementing skills that write files, the approval gate was skipped in an early prototype, leading to unreviewed writes during testing.

## Why it matters

Without the gate, lesson files accumulate noise — half-formed observations and task-local notes that should have been filtered. The review-lessons skill then has to sift through low-quality candidates.

## How to apply

Always show the approval gate before writing any lesson file, in both on-demand and session-end modes. The gate is the quality filter; it is not optional.
```

- [ ] **Step 2: Create the feedback fixture**

Create `tests/fixtures/capture-lesson-output/lessons/feedback/test-feedback.md`:

```markdown
---
id: memex:lesson:test-feedback
title: Feedback lessons preserve user direction verbatim
stream: feedback
status: draft
tags: [test, feedback-stream]
created: 2026-05-10
---

## Observation

User stated: "Always route user corrections to feedback, not inbox — I want to be able to find my own directions separately."

## Why it matters

Feedback stream lessons carry higher priority than AI-inferred lessons. Mixing them into inbox makes review harder and risks treating user direction as a mere suggestion.

## How to apply

When the user explicitly states a correction, preference, or direction, route to `lessons/feedback/` not `lessons/inbox/`. Default ambiguous cases to inbox.
```

- [ ] **Step 3: Write the test file**

Create `tests/test_capture_lesson_skill.py`:

```python
import pathlib
import frontmatter as fm

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures" / "capture-lesson-output"
INBOX_LESSON = FIXTURES_DIR / "lessons" / "inbox" / "test-lesson.md"
FEEDBACK_LESSON = FIXTURES_DIR / "lessons" / "feedback" / "test-feedback.md"
SKILL_MD = pathlib.Path(__file__).parent.parent / "skills" / "capture-lesson" / "SKILL.md"
REFERENCE_MD = pathlib.Path(__file__).parent.parent / "skills" / "capture-lesson" / "REFERENCE.md"
LESSON_FORMAT_MD = pathlib.Path(__file__).parent.parent / "docs" / "LESSON_FORMAT.md"


def test_inbox_lesson_parses_correctly():
    """Inbox fixture must parse with correct id, stream, status, tags, and body."""
    post = fm.load(str(INBOX_LESSON))
    assert post.metadata["id"] == "memex:lesson:test-lesson"
    assert post.metadata["stream"] == "inbox"
    assert post.metadata["status"] == "draft"
    assert "test" in post.metadata["tags"]
    assert "Observation" in post.content


def test_feedback_lesson_parses_correctly():
    """Feedback fixture must parse with stream=feedback and required body sections."""
    post = fm.load(str(FEEDBACK_LESSON))
    assert post.metadata["id"] == "memex:lesson:test-feedback"
    assert post.metadata["stream"] == "feedback"
    assert post.metadata["status"] == "draft"
    assert "Observation" in post.content


def test_lesson_id_format():
    """id must follow <project>:lesson:<slug> with type='lesson'."""
    for path in [INBOX_LESSON, FEEDBACK_LESSON]:
        post = fm.load(str(path))
        parts = post.metadata["id"].split(":")
        assert len(parts) == 3, f"id must be <project>:lesson:<slug>, got {post.metadata['id']}"
        assert parts[1] == "lesson", f"id type must be 'lesson', got {parts[1]}"


def test_lesson_status_is_draft():
    """New lessons must always have status=draft."""
    for path in [INBOX_LESSON, FEEDBACK_LESSON]:
        post = fm.load(str(path))
        assert post.metadata["status"] == "draft"


def test_lesson_body_has_required_sections():
    """Body must contain all three required sections."""
    for path in [INBOX_LESSON, FEEDBACK_LESSON]:
        post = fm.load(str(path))
        assert "Observation" in post.content
        assert "Why it matters" in post.content
        assert "How to apply" in post.content


def test_skill_md_under_150_lines():
    """SKILL.md must stay ≤150 lines."""
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
    """skills/capture-lesson/REFERENCE.md must exist."""
    assert REFERENCE_MD.exists(), "skills/capture-lesson/REFERENCE.md must exist"


def test_lesson_format_doc_exists():
    """docs/LESSON_FORMAT.md must exist."""
    assert LESSON_FORMAT_MD.exists(), "docs/LESSON_FORMAT.md must exist"
```

- [ ] **Step 4: Run tests — expect 5 pass, 4 fail**

Run from `C:\Users\user\Documents\Skills\memex`:
```
pytest tests/test_capture_lesson_skill.py -v
```
Expected: tests 1–5 pass (fixtures valid); tests 6–9 fail (SKILL.md, REFERENCE.md, LESSON_FORMAT.md not yet created).

- [ ] **Step 5: Commit fixtures and test file**

```bash
git add tests/fixtures/capture-lesson-output/lessons/inbox/test-lesson.md
git add tests/fixtures/capture-lesson-output/lessons/feedback/test-feedback.md
git add tests/test_capture_lesson_skill.py
git commit -m "test: capture-lesson skill — fixtures and test file (5/9 pass)"
```

---

## Task 2: Write docs/LESSON_FORMAT.md

**Files:**
- Create: `docs/LESSON_FORMAT.md`

- [ ] **Step 1: Write LESSON_FORMAT.md**

Create `docs/LESSON_FORMAT.md`:

```markdown
# Lesson Format

Lessons are markdown files with YAML frontmatter. They live in `lessons/inbox/` (AI-captured suggestions) or `lessons/feedback/` (user-direct feedback).

## Frontmatter

---
id: <project>:lesson:<slug>
title: <title>
stream: inbox | feedback
status: draft | promoted | discarded
tags: [...]
created: YYYY-MM-DD
---

## Body

## Observation

What happened or was noticed. For feedback stream: the user's stated direction verbatim or close to it.

## Why it matters

The non-obvious implication. What would go wrong without this lesson.

## How to apply

Concrete guidance for next time.

## Filename

`lessons/<stream>/<slug>.md` — slug is kebab-case, derived from title.

## Lifecycle

| Status | Meaning |
|---|---|
| `draft` | Awaiting review. All new lessons start here. |
| `promoted` | Substance promoted into a wiki entry, methodology, or skill update. File moved to `lessons/promoted/`. |
| `discarded` | Reviewed and rejected. Default action: delete. Set `discard-reason` if reason needs logging. |

## Streams

| Stream | Path | When used |
|---|---|---|
| `inbox` | `lessons/inbox/<slug>.md` | AI-captured suggestions — require review before acting on |
| `feedback` | `lessons/feedback/<slug>.md` | User-direct feedback — treated as direction, higher priority than inbox |
```

- [ ] **Step 2: Run tests — expect 6 pass, 3 fail**

```
pytest tests/test_capture_lesson_skill.py -v
```
Expected: test 9 (`test_lesson_format_doc_exists`) now passes. Tests 6, 7, 8 still fail.

- [ ] **Step 3: Commit**

```bash
git add docs/LESSON_FORMAT.md
git commit -m "docs: lesson format reference"
```

---

## Task 3: Write skills/capture-lesson/REFERENCE.md

**Files:**
- Create: `skills/capture-lesson/REFERENCE.md`

- [ ] **Step 1: Write REFERENCE.md**

Create `skills/capture-lesson/REFERENCE.md`:

```markdown
# capture-lesson — Reference

## Frontmatter fields

### Required

| Field | Type | Notes |
|---|---|---|
| `id` | string | `<project>:lesson:<slug>`. Type is always `lesson`. Immutable after creation. Never reuse a deleted slug. Prompt if uncertain — never guess. On REPAIR: re-derived as if NEW. |
| `title` | string | Human-readable. Sentence case. |
| `stream` | enum | `inbox` / `feedback`. Auto-routed (see Stream routing). Set at creation; never changed on UPDATE. |
| `status` | enum | `draft` / `promoted` / `discarded`. Always `draft` on NEW or REPAIR. Preserved unchanged on UPDATE. |
| `created` | YYYY-MM-DD | Set to today on NEW or REPAIR; preserved on UPDATE. |

### Optional

| Field | Type | Notes |
|---|---|---|
| `slug` | string | Include only when it differs from the filename stem; omit otherwise. |
| `tags` | string[] | Categorization labels. |

---

## Body structure

```
## Observation

<What happened or was noticed. For feedback stream: user's stated direction verbatim or close to it.>

## Why it matters

<The non-obvious implication. What would go wrong without this lesson.>

## How to apply

<Concrete guidance for next time.>
```

---

## Stream routing

| Origin | Stream | Path |
|---|---|---|
| AI proposes the lesson unprompted | `inbox` | `lessons/inbox/<slug>.md` |
| User explicitly states feedback, correction, or direction | `feedback` | `lessons/feedback/<slug>.md` |
| Ambiguous | `inbox` (default) | `lessons/inbox/<slug>.md` |

---

## REPAIR path

REPAIR triggers when: (a) YAML frontmatter cannot be parsed, OR (b) one or more required fields (`id`, `title`, `stream`, `status`) are absent or empty. On REPAIR, all fields are re-derived as if NEW from the current conversation.

---

## Commit message formats

| Mode | Format |
|---|---|
| On-demand (single lesson) | `lessons: capture — <title>` |
| Session-end (batch) | `lessons: capture — N lessons` |

> **Note:** Commit messages use the Unicode em dash (U+2014, `—`). Before committing: run `git config i18n.commitEncoding`. If output is empty, `utf-8`, `utf8`, `UTF-8`, or `UTF8` — use em dash. Any other value — substitute `--` (ASCII double-hyphen).

---

## Error table

| Situation | Action |
|---|---|
| No `lessons/inbox/` at project root | Stop: "No lessons directory found. Create `lessons/inbox/` and `lessons/feedback/` in your project root before running capture-lesson." |
| Multiple detectable projects | Ask user which project to target. Wait for explicit choice. |
| Existing file malformed | REPAIR path: re-derive all fields as if NEW. Gate shows `[REPAIR: previous write failed — re-drafted from conversation]`. |
| `git commit` fails | Show error, do not retry. Written files remain on disk uncommitted. |
| Session-end sweep finds no candidates | Report "No lesson candidates found in this session." Done. |
```

- [ ] **Step 2: Run tests — expect 7 pass, 2 fail**

```
pytest tests/test_capture_lesson_skill.py -v
```
Expected: test 8 (`test_reference_md_exists`) now passes. Tests 6 and 7 still fail (SKILL.md missing).

- [ ] **Step 3: Commit**

```bash
git add skills/capture-lesson/REFERENCE.md
git commit -m "feat: capture-lesson REFERENCE.md"
```

---

## Task 4: Write skills/capture-lesson/SKILL.md

**Files:**
- Create: `skills/capture-lesson/SKILL.md`

- [ ] **Step 1: Write SKILL.md**

Create `skills/capture-lesson/SKILL.md`. Must be ≤150 lines and description ≤1024 chars:

```markdown
---
description: "Use when the user wants to capture a lesson from the current session — either on demand (\"capture this as a lesson\", \"I noticed X\") or at session end to review and propose lessons from the conversation. Also use when the user invokes /capture-lesson. Do NOT use for writing wiki pages (use capture) or reviewing and promoting lessons (use review-lessons)."
---

# capture-lesson — write a lesson file

## Mode detection

- **On-demand** — user provides a topic, observation, or points to something from the conversation. Handle first.
- **Session-end** — user invokes with no specific topic ("what lessons should we capture?", `/capture-lesson` with no args).

Both modes share the approval gate. Commit behavior differs by mode.

**After detecting mode**, confirm the target project root:

- **Zero detectable projects** (no `lessons/inbox/` at any accessible root): stop. Tell the user: 'No lessons directory found. Create `lessons/inbox/` and `lessons/feedback/` in your project root before running capture-lesson.' Do not create directories automatically. Do not proceed.
- **Exactly one detectable project**: proceed. Announce: 'Writing to `<path>/lessons/`.' No confirmation needed.
- **More than one detectable project**: ask the user which project. Wait for explicit choice.

A project is detectable if it contains `lessons/inbox/` at its root — check each root at this fixed path only. Do not recurse.

---

## On-demand mode

1. **Extract content** from user input / conversation:
   - `id`: `<project>:lesson:<slug>` — prompt if uncertain; never guess
   - `title`, `slug` (include only if it differs from the filename stem; omit otherwise), `tags`, `stream` (auto-routed — see REFERENCE.md), `status` (always `draft` on NEW or REPAIR)
   - Body: Observation / Why it matters / How to apply

2. **Check for existing file** at `lessons/<stream>/<slug>.md`:
   - Not found → prepare NEW
   - Found → read it; prepare diff summary (one line per changed field; body changes as `body: content updated`)
   - Found but malformed (unparseable YAML or required field absent) → REPAIR: re-derive all fields as if NEW; gate shows `[REPAIR: previous write failed — re-drafted from conversation]`

3. **Show approval gate:**
   ```
   Will write: lessons/<stream>/<slug>.md
   Title: <title>
   Stream: <stream>  |  Tags: [...]
   ~<N> lines
   [NEW]  or  [UPDATE: <summary>]  or  [REPAIR: previous write failed — re-drafted from conversation]
   Approve? (yes / edit / skip / cancel)
   ```
   - **yes** → step 4
   - **edit** → apply correction, re-show gate
   - **skip** / **cancel** / **abort** → stop, write nothing
   - Any other message → treat as edit instruction

4. **On approval** → write file (field rules in REFERENCE.md), stage it, commit: `lessons: capture — <title>`

---

## Session-end mode

1. **Sweep** the conversation for lesson candidates:
   - Non-obvious observations, mid-session corrections, decisions with a "why", patterns that would help a future AI avoid a mistake
   - Skip: task-local notes, anything obvious from code or git history, ephemeral state

2. **Show candidate list** before any gates:
   ```
   Found N lesson candidates:
   1. <title> (inbox)
   2. <title> (feedback)
   Proceed through each? (yes / skip N / cancel)
   ```
   - **yes** → gate each in order
   - **skip N** → exclude candidate N, gate the rest
   - **cancel** → stop, write nothing
   - No candidates found → report "No lesson candidates found in this session." Done.

3. **Gate each candidate** one at a time — same approval gate as on-demand.

4. **After all gates** → stage all approved lessons; one commit: `lessons: capture — N lessons`

---

## Error handling

See REFERENCE.md error table and commit message format.
```

- [ ] **Step 2: Count lines to verify ≤150**

```
(Get-Content skills\capture-lesson\SKILL.md).Count
```
Expected: a number ≤ 150.

- [ ] **Step 3: Run all 9 tests — expect all pass**

```
pytest tests/test_capture_lesson_skill.py -v
```
Expected: all 9 tests PASS.

- [ ] **Step 4: Run full test suite to check for regressions**

```
pytest tests/ -v
```
Expected: all tests pass (no regressions in rebuild, sync, capture, ask tests).

- [ ] **Step 5: Commit**

```bash
git add skills/capture-lesson/SKILL.md
git commit -m "feat: capture-lesson skill v0"
```
