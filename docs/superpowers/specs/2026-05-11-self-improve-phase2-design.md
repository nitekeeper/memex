# Self-Improve Phase 2 — Design Spec

> Builds on Phase 1 (session-start queue-processing pass, shipped 2026-05-11).

---

## Goal

Add an explicit `self-improve` skill that lets Claude run the full self-improvement loop either autonomously (solo) or collaboratively with the user — on demand, mid-session.

---

## Architecture

**New file:** `skills/self-improve/SKILL.md`
**Modified file:** `skills/review-lessons/SKILL.md`

The `self-improve` skill is a unified entry point with two modes. Mode is detected from invocation phrasing:

- **Solo** — "run self-improve solo", "self-improve on your own", "do self-improvement alone", or similar. Full pipeline with filtering. No gates.
- **Collaborative** — "let's run self-improve", "self-improve together", "run self-improve with me", or similar. Orchestrates existing skills with their gates intact.

Existing skills (`capture-lesson`, `review-lessons`, `propose-wiki-entry`) are unchanged except for the `review-lessons` update below.

---

## Solo mode

### Trigger

Invoked explicitly by the user mid-session. Requires an active conversation to sweep for candidates.

### Pipeline (no gates)

**Step 1 — Capture**
Sweeps the current conversation for lesson candidates using the same logic as `capture-lesson` session-end mode. Skips any candidate whose slug already exists in `lessons/` or `.ai/wiki/`.

**Step 2 — Filter**
Each candidate is evaluated against three signals. Any one triggers a hold:

| Signal | Condition |
|---|---|
| Contradiction | Conflicts with an existing approved wiki entry in `.ai/wiki/` |
| Philosophy/goals | Touches goals, priorities, design direction, or methodology |
| Low confidence | Claude would naturally phrase it as "I think", "it seems", or "possibly" |

- **Confident candidates** → written to `lessons/inbox/` as `status: draft` (normal flow)
- **Held candidates** → written to `lessons/inbox/` as `status: draft` with extra frontmatter:

```yaml
held-for-review: true
held-reason: contradiction | philosophy | confidence
```

**Step 3 — Review + propose (solo)**
Runs `review-lessons` and `propose-wiki-entry` in solo mode (no gates) on newly captured confident lessons only. Held items remain as drafts for the next collaborative session.

**Step 4 — Summary**
Always shown after the run:

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

---

## Collaborative mode

### Trigger

Invoked explicitly by the user mid-session.

### Mode selection

Upon invocation, ask:

```
Self-improve — collaborative mode.
What would you like to do?
a) Full loop — capture new lessons from this conversation, then review everything together
b) Queue review — review held items and existing drafts (no fresh capture)
```

### Option a — Full loop

1. Run `capture-lesson` (session-end mode, with gates) — user approves each candidate
2. Run `review-lessons` (with gates, held items first) — promote / discard / defer
3. Run `propose-wiki-entry` (with gates) — convert promoted lessons to wiki drafts

### Option b — Queue review

1. Skip capture
2. Run `review-lessons` (with gates, held items first) — promote / discard / defer
3. Run `propose-wiki-entry` (with gates) — convert promoted lessons to wiki drafts

In both options, held items surface at the top of `review-lessons` with their `held-reason` shown.

---

## `review-lessons` update

### Scan order change

Current: feedback drafts → inbox drafts

Updated: held items first (feedback stream before inbox), then regular drafts (feedback before inbox).

A lesson is "held" if its frontmatter contains `held-for-review: true`.

### Review block update

For held items, the review block gains a `[HELD: <reason>]` marker and a `Held reason:` line:

```
--- Lesson N of N --- [HELD: <reason>]
Title: <title>
Stream: <stream>  |  Tags: [...]

Held reason: <contradiction with <wiki-slug> | touches philosophy/goals | low confidence>
How to apply: <content>

Action? (promote / discard / defer)
```

Regular draft items are unchanged.

### Candidate list

The candidate list shown before review gains a `[HELD]` tag for held items:

```
Found N draft lessons (H held, F feedback, I inbox):
1. <title> (feedback) [HELD: philosophy]
2. <title> (inbox) [HELD: contradiction]
3. <title> (feedback)
4. <title> (inbox)
Proceed? (yes / cancel)
```

---

## Skill CSO description

```
Use when the user wants to run the self-improvement loop — either solo (Claude runs it autonomously without gates) or collaboratively (user and Claude work through it together with approval at each step). Trigger on: "self-improve", "run self-improve", "self-improvement loop", "run the loop solo", "let's do self-improve together", "self-improve on your own", "review our lessons together". Also trigger when the user asks Claude to capture and review lessons as a batch in one invocation.
```

---

## Files changed

| File | Change |
|---|---|
| `skills/self-improve/SKILL.md` | New — unified solo + collaborative skill |
| `skills/review-lessons/SKILL.md` | Update scan order + review block for held items |
| `dist/` | Not updated here — release is a separate deliberate step per Working Rule 5 |

---

## Success criteria

- "Run self-improve solo" → full pipeline runs without gates, held items flagged, summary shown
- "Let's run self-improve together" → mode choice presented, existing skill gates intact
- Held items surface first in collaborative `review-lessons` with reason shown
- No existing skill behavior changed outside of `review-lessons` scan order
- `held-for-review` and `held-reason` fields written correctly to lesson files
