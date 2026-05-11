# Self-Improve — Design Spec

> Phase 1 scoped. Phase 2 outlined for future planning.

---

## Goal

Give Claude the ability to run the Memex self-improvement loop autonomously, without requiring the user to manually invoke each skill. Two modes:

- **Autonomous (solo)** — Claude runs the pipeline without gates, writes what it's confident about, holds uncertain items for collaborative review, shows a summary.
- **Collaborative** — user invokes the loop and works through it together with Claude, with full approval gates at every step (existing behavior, unchanged).

---

## Phase 1 — Session-start queue-processing pass

### What it is

When a new session opens in a Memex-enabled project, Claude automatically processes the lessons queue before the user starts working. No new skill is required — Phase 1 is orchestration of existing skills plus a CLAUDE.md instruction.

### Trigger mechanism

A CLAUDE.md instruction added to the Memex product tells Claude to run the queue-processing pass at session start. Claude reads CLAUDE.md on open and follows the instruction. No shell hook, no external scheduler.

### Pipeline

Runs in order, without approval gates:

1. **`review-lessons`** (solo) — sweep `lessons/feedback/` then `lessons/inbox/` for `status: draft` lessons. Promote lessons that are clearly factual, non-conflicting, and non-philosophical. Discard if obviously stale or redundant. Defer anything uncertain.
2. **`propose-wiki-entry`** (solo) — convert all newly promoted lessons into draft wiki entries in `.ai/wiki/`.
3. **`sync`** — surface wiki entries whose tracked source files have drifted since `synced-at-commit`.

### Summary format

Always shown after the pass completes:

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

If nothing was in the queue: `Session-start pass — nothing in queue. Ready.`

### What "solo review" means in Phase 1

Phase 1 does not yet implement the full confidence/contradiction filtering logic (Phase 2). In Phase 1, solo review applies a simpler heuristic:

- **Promote** if the lesson is factual and self-contained (a clear observation with a concrete how-to-apply)
- **Defer** if the lesson touches goals, priorities, design philosophy, or contradicts an existing wiki entry
- **Discard** if the lesson duplicates something already in the wiki or is purely session-local

Deferred lessons stay in `lessons/inbox/` as `status: draft`. They appear in the summary and are picked up naturally by the next collaborative `review-lessons` run.

### CLAUDE.md entry

Added to the Memex product CLAUDE.md under a new "Session start" section:

```
## Session start

At the start of every session, run the self-improvement queue-processing pass:
1. Run `review-lessons` in solo mode (no gates) — promote clear lessons, defer uncertain ones.
2. Run `propose-wiki-entry` in solo mode (no gates) — convert promoted lessons to wiki drafts.
3. Run `sync` — flag stale wiki entries.
4. Show the summary.

Do this before responding to the user's first message.
```

### Files changed

| File | Change |
|---|---|
| `CLAUDE.md` (Memex product) | Add session-start instruction |
| Existing skills | No changes |

---

## Phase 2 — Full self-improve skill (future)

Builds on Phase 1. Adds:

- **`skills/self-improve/SKILL.md`** — unified entry point for both solo and collaborative modes
- **Solo mode** — full confidence/contradiction/philosophy filtering; held items written to `lessons/inbox/` with `held-for-review: true` and `held-reason` frontmatter fields
- **Collaborative mode** — chains existing skills with full approval gates; invoked when user wants to review together ("let's run self-improve together")
- **Explicit solo invocation** — user can trigger solo mode on-demand mid-session ("run self-improve solo")

Phase 2 is not scoped here. Design deferred to next planning session after Phase 1 is validated.

---

## Success criteria for Phase 1

- Opening a Memex-enabled project triggers the queue-processing pass automatically
- Summary is shown before the user's first exchange
- Existing skills and their approval gates are unchanged
- Deferred lessons remain in the inbox for the next collaborative session
- No lessons or wiki entries are written without passing the solo heuristic
