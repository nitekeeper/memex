# Self-Improve Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a session-start queue-processing pass to the Memex product so Claude automatically runs `review-lessons` → `propose-wiki-entry` → `sync` and shows a summary before the user's first message.

**Architecture:** A new "Session start" section in `CLAUDE.md` instructs Claude to run the queue-processing pass on open. No new skills are written — Phase 1 orchestrates existing skills. Working rule 4 is updated to clarify that the session-start pass is the exception to the mid-session approval gate.

**Tech Stack:** Markdown (CLAUDE.md), existing Memex skills (`review-lessons`, `propose-wiki-entry`, `sync`)

---

### Task 1: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (Memex product root)

- [ ] **Step 1: Read the current CLAUDE.md**

Confirm the file at `CLAUDE.md` (Memex product root). Note the current working rule 4:
> "Propose wiki entries during sessions; approve at session close. Do not unilaterally edit `.ai/wiki/` mid-flow."

- [ ] **Step 2: Add the session-start section**

Insert a new `## Session start` section immediately after the `## Read at session start` section:

```markdown
## Session start

Before responding to the user's first message, run the self-improvement queue-processing pass:

1. **`review-lessons` (solo)** — scan `lessons/feedback/` then `lessons/inbox/` for `status: draft` lessons.
   - **Promote** if the lesson is factual, self-contained, and has a concrete how-to-apply.
   - **Defer** (leave as draft) if the lesson touches goals, priorities, design philosophy, or contradicts an existing approved wiki entry.
   - **Discard** if it duplicates something already in the wiki or is purely session-local.
   - Apply actions directly — no approval gate.

2. **`propose-wiki-entry` (solo)** — convert all newly promoted lessons into draft wiki entries in `.ai/wiki/`. Apply directly — no approval gate.

3. **`sync`** — run `python scripts/sync.py .ai/` from the Memex product root to surface stale wiki entries.

4. **Show summary** using this exact format:

   ```
   Session-start self-improvement pass — YYYY-MM-DD
     Lessons reviewed: N
       Promoted: X
       Deferred (needs collaborative review): Y
       Discarded: Z
     Wiki entries proposed: M
     Stale entries flagged: K
       - <title> (.ai/wiki/<slug>.md)
   ```

   If nothing was in the queue, show: `Session-start pass — nothing in queue. Ready.`

5. **Commit all changes** from the pass in a single commit:
   `chore: session-start self-improvement pass — YYYY-MM-DD`

Then wait for the user's first message.
```

- [ ] **Step 3: Update working rule 4**

Replace the current working rule 4:
```
4. **Propose wiki entries during sessions; approve at session close.** Do not unilaterally edit `.ai/wiki/` mid-flow.
```

With:
```
4. **Propose wiki entries during sessions; approve at session close.** Do not unilaterally edit `.ai/wiki/` mid-flow. Exception: the session-start queue-processing pass (see Session start section) may write wiki drafts and promote lessons autonomously — this is the only context where gates are bypassed.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "feat: add session-start self-improvement queue-processing pass"
```

Expected output: 1 file changed, ~40 insertions(+), 1 deletion(-)

---

### Task 2: Manual verification

**Files:** None — observational test only.

- [ ] **Step 1: Seed the inbox with at least one draft lesson**

If `lessons/inbox/` is empty, create a minimal test lesson:

```bash
cat > lessons/inbox/test-session-start.md << 'EOF'
---
id: memex:lesson:test-session-start
title: Test lesson for session-start verification
stream: inbox
tags: [test]
status: draft
created: 2026-05-11
---

## Observation
This lesson exists to verify that the session-start queue-processing pass picks up draft lessons automatically.

## Why it matters
Without a seeded lesson, the session-start pass has nothing to process and we cannot verify it ran.

## How to apply
Delete this lesson after verification is complete.
EOF
git add lessons/inbox/test-session-start.md
git commit -m "test: seed inbox with verification lesson"
```

- [ ] **Step 2: Open a new Claude Code session in the Memex product root**

Start a fresh session. Do not say anything yet — wait for Claude to run the session-start pass automatically.

- [ ] **Step 3: Verify the summary appears**

Expected: Claude shows the queue-processing summary before responding to any user input. The summary should show at least 1 lesson reviewed.

- [ ] **Step 4: Verify the commit was made**

```bash
git log --oneline -3
```

Expected: top commit is `chore: session-start self-improvement pass — YYYY-MM-DD`

- [ ] **Step 5: Clean up test lesson**

If the test lesson was promoted to `lessons/promoted/` or written to `.ai/wiki/`, verify the content is sensible (it should be deferred or discarded since it's flagged as a test artifact). Remove any test artifacts:

```bash
git rm lessons/inbox/test-session-start.md 2>/dev/null || true
git rm lessons/promoted/test-session-start.md 2>/dev/null || true
git rm .ai/wiki/test-session-start.md 2>/dev/null || true
git commit -m "test: remove session-start verification lesson" --allow-empty
```

---

## Success criteria

- [ ] New session opens → queue-processing summary shown before first user message
- [ ] Draft lessons in inbox are promoted, deferred, or discarded correctly
- [ ] Promoted lessons become draft wiki entries in `.ai/wiki/`
- [ ] Stale wiki entries are flagged (if any)
- [ ] All changes committed in a single `chore: session-start` commit
- [ ] Nothing written silently without the summary being shown
