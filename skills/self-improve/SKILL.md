---
description: "Use when the user wants to run the self-improvement loop — either solo (Claude runs it autonomously without gates) or collaboratively (user and Claude work through it together with approval at each step). Trigger on: \"self-improve\", \"run self-improve\", \"self-improvement loop\", \"run the loop solo\", \"let's do self-improve together\", \"self-improve on your own\". Also trigger when the user asks Claude to capture and review lessons as a batch in one invocation."
---

# self-improve — run the self-improvement loop

## Mode detection

Detect mode from invocation phrasing:
- **Solo** — "run self-improve solo", "self-improve on your own", "do it yourself", or similar autonomous framing.
- **Collaborative** — "let's self-improve", "let's run self-improve", "self-improve together", "run self-improve with me", or similar joint framing.

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
| Contradiction | Conflicts with an existing `status: approved` wiki entry in `.ai/wiki/` (if `.ai/wiki/` does not exist, skip this check — treat as no conflicts) |
| Philosophy/goals | Touches goals, priorities, design direction, or methodology |
| Low confidence | Would naturally be phrased as "I think", "it seems", or "possibly" |

If multiple signals apply to one candidate, write the highest-priority reason: `contradiction` > `philosophy` > `confidence`.

- **Confident candidates** → write to `lessons/inbox/<slug>.md` as `status: draft`
- **Held candidates** → write to `lessons/inbox/<slug>.md` as `status: draft` plus `held-for-review: true` and `held-reason: contradiction | philosophy | confidence` (see REFERENCE.md for format)

### Step 3 — Review + propose (solo, no gates)

If no confident candidates were written in Step 2 (X = 0), skip to Step 4.

Before reviewing, exclude any lesson file where `held-for-review: true` — operate only on files where this field is absent or false. Then for each remaining confident draft lesson, apply these heuristics directly without gates:
- **Promote** if the lesson is factual, self-contained, and has a concrete how-to-apply
- **Defer** (leave as draft) if ambiguous or requires context not available in this session
- **Discard** if it duplicates something already in `lessons/` or `.ai/wiki/`, or is purely session-local

Then run `propose-wiki-entry` solo on any promoted lessons.
If no lessons were promoted, skip `propose-wiki-entry` and show `Wiki entries proposed: 0` in the summary.

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
1. Run `capture-lesson` (session-end mode)
2. Run `review-lessons` (held items surface first)
3. Run `propose-wiki-entry`

**Option b — Queue review:**
1. Run `review-lessons` (held items surface first)
2. Run `propose-wiki-entry`

Each skill runs its own approval gates. Nothing is written without user confirmation.
