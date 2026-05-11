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

Em dash: use literal `—` (U+2014), not `--`. See also `capture-lesson/REFERENCE.md` for the encoding check procedure.

## Error handling

| Situation | Action |
|---|---|
| Solo mode, no active conversation | Tell user: 'Solo mode requires an active conversation. Start a session first.' Stop. |
| No detectable project | Tell user: 'No lessons directory found. Create `lessons/inbox/` in your project root.' Stop. |
| Multiple detectable projects | Ask user which project. Wait for explicit choice. |
