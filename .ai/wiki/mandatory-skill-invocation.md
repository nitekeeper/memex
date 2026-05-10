---
id: memex:wiki:mandatory-skill-invocation
slug: mandatory-skill-invocation
title: Mandatory invocation enforced by anti-rationalization tables
status: approved
tags: [skill-authoring, governance, invocation, anti-rationalization]
sources: [source:superpowers-skill-system]
related: [memex:wiki:skill-cso-description-trap]
proposed-in: session:2026-05-09
approved-in: session:2026-05-09
created: 2026-05-09
updated: 2026-05-09
---

# Mandatory invocation enforced by anti-rationalization tables

The governing rule for skill invocation is: if there is even a 1% chance a skill applies, invoke it. This rule must be paired with an explicit anti-rationalization table — a list of common excuses the LLM uses to avoid invocation, with refutations. Without the table, the rule degrades under cognitive load.

## The 1% rule

> "If you think there is even a 1% chance a skill might apply, you ABSOLUTELY MUST invoke the skill."

The threshold is deliberately low. Skills are cheap to invoke and expensive to skip — a missed invocation means the LLM operates without methodology guidance for the rest of the task. The asymmetry justifies the low threshold.

## Why the table is load-bearing

The rule alone is not enough. Under pressure (complex task, time constraint, mid-flow), the LLM generates plausible-sounding reasons not to invoke. The anti-rationalization table pre-empts these by naming them explicitly. A named excuse is harder to act on than an unnamed one.

| Rationalization | Reality |
|---|---|
| "This is just a simple question" | Questions are tasks. Check for skills. |
| "I need more context first" | Skill check comes before clarifying questions. |
| "I remember this skill" | Skills evolve. Read the current version. |
| "This doesn't need a formal skill" | If a skill exists, use it. |
| "The skill is overkill" | Simple things become complex. Use it. |
| "I'll just do this one thing first" | Check before doing anything. |

## How to apply in Memex skills

- Every Memex skill that governs a discipline (not just a reference) includes an anti-rationalization table in its body.
- The root skill (or `meta:run-session` equivalent) carries the 1% rule and the master rationalization table.
- Skill descriptions state only triggering conditions (see `wiki:skill-cso-description-trap`) so the LLM cannot rationalize away from reading the body.

## Failure modes

- **Table without the rule.** The table lists excuses but the governing threshold is vague ("use when relevant"). The LLM still rationalizes at the margin. Mitigation: state the threshold explicitly (1%, not "when applicable").
- **Rule without the table.** The rule is stated but the LLM generates novel excuses not covered. Mitigation: add excuses to the table as they are observed (the TDD-for-docs refactor cycle).
- **Invocation theater.** The skill is invoked but the content is skimmed rather than followed. Mitigation: hard gates block forward progress on specific actions until the skill's conditions are met.

## References

- `source:superpowers-skill-system` — `using-superpowers` skill; rationalization table; 1% rule.
- `wiki:skill-cso-description-trap` — descriptions must not provide a shortcut that bypasses invocation.
- `wiki:tdd-for-skill-authoring` — rationalization tables are populated from baseline testing, not invented upfront.
