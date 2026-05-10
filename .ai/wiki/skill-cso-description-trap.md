---
id: memex:wiki:skill-cso-description-trap
slug: skill-cso-description-trap
title: Skill descriptions that summarize workflow shortcircuit the skill body
status: approved
tags: [skill-authoring, cso, description, context-injection]
sources: [source:superpowers-skill-system]
related: [memex:wiki:two-tier-instruction-loading]
proposed-in: session:2026-05-09
approved-in: session:2026-05-09
created: 2026-05-09
updated: 2026-05-09
---

# Skill descriptions that summarize workflow shortcircuit the skill body

A skill description must state only *when* to use the skill — never *what it does* or *how it works*. When a description summarizes the workflow, the LLM follows the description as a shortcut and skips reading the full skill body.

## The empirical case

Superpowers tested this directly on `subagent-driven-development`:

- Description: "dispatches subagent per task with code review between tasks" → LLM performed **one** review (following the description's summary).
- Description: "Use when executing implementation plans with independent tasks" → LLM performed **two** reviews (per the flowchart in the skill body).

Same skill body. Different descriptions. The description determined behavior, not the skill content.

## The rule

```
Description = when to use (triggering conditions)
Description ≠ what the skill does
Description ≠ how the skill works
```

**Start with "Use when…"** and describe the situation the user is in, not the procedure the skill runs.

```yaml
# Bad — summarizes workflow
description: Use when executing plans — dispatches subagent per task with two-stage review

# Good — triggering conditions only
description: Use when executing implementation plans with independent tasks
```

## Why it happens

The LLM reads the description to decide whether to load the skill. Once it has loaded the skill, the description is still in context — if it contains a workflow summary, that summary is a shorter, more salient instruction than the full skill body. The LLM optimizes toward the shorter instruction.

## How to apply

- Write the description last, after the skill body is complete.
- Read the description in isolation: does it tell you how to do the task? If yes, strip that content out.
- The test: could a reader follow the description alone and produce roughly correct behavior? If yes, the description is too detailed.
- Maximum ~500 characters; aim for one sentence.

## Failure modes

- **"Use when X — do Y, then Z."** The "do Y, then Z" part is workflow. Cut it.
- **Describing outputs.** "Use when building features — produces a spec and a plan." The second clause is workflow. Cut it.
- **Listing steps.** Any enumeration in the description is a red flag.

## References

- `source:superpowers-skill-system` — CSO section of `writing-skills`; empirical test on `subagent-driven-development`.
- `wiki:two-tier-instruction-loading` — related principle: lean always-loaded content, heavy content deferred.
- `docs/SKILL_FORMAT.md` — description field rules.
