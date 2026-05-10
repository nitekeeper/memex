---
id: memex:wiki:tdd-for-skill-authoring
slug: tdd-for-skill-authoring
title: Skill authoring follows RED-GREEN-REFACTOR
status: approved
tags: [skill-authoring, tdd, testing, anti-rationalization]
sources: [source:superpowers-skill-system]
related: [memex:wiki:mandatory-skill-invocation, memex:wiki:skill-cso-description-trap]
proposed-in: session:2026-05-09
approved-in: session:2026-05-09
created: 2026-05-09
updated: 2026-05-09
---

# Skill authoring follows RED-GREEN-REFACTOR

Creating a skill is TDD applied to process documentation. The cycle is identical: write a failing test first (baseline scenario without the skill), write the minimal skill to make it pass, refactor by closing loopholes as new failures emerge.

## The cycle

**RED — baseline without the skill**

Run a pressure scenario using a fresh LLM instance with no skill loaded. Document verbatim:
- What choices did the LLM make?
- What rationalizations did it produce?
- Which pressures triggered violations?

This is the failing test. You must watch the failure before writing the skill.

**GREEN — write the minimal skill**

Write only what is needed to address the specific failures observed in RED. Do not add content for hypothetical cases. Run the same scenario with the skill loaded. The LLM should now comply.

**REFACTOR — close loopholes**

The LLM will find new rationalizations not covered by the initial skill. Each new rationalization goes into the anti-rationalization table. Re-test after each addition. Repeat until the skill holds under maximum pressure.

## Why baseline testing is non-negotiable

A skill written without a baseline test encodes the author's assumptions about how the LLM will fail, not how it actually fails. The assumptions are almost always wrong in detail. The rationalization table (see `wiki:mandatory-skill-invocation`) is only useful if it was populated from real failures — invented excuses miss the actual failure modes.

## Pressure types to test

For discipline-enforcing skills (rules, gates, verification requirements), combine multiple pressures:
- **Time pressure** — "we're almost out of context, just do it quickly"
- **Sunk cost** — "we've already done so much, let's not slow down now"
- **Simplicity claim** — "this case is too simple to need the skill"
- **Authority bypass** — "I'm telling you it's fine to skip it"

Single-pressure tests are insufficient; real violations happen under combinations.

## What this means for Memex

- Before shipping any Memex skill (capture, sync, search), run baseline scenarios.
- The anti-rationalization tables in those skills are populated from the baseline results, not written speculatively.
- Refactor cycles are expected — the first version of a skill will have gaps.

## Failure modes

- **Writing the skill before the baseline.** The skill addresses imagined failures, not real ones. No exceptions: baseline first.
- **Single-pressure testing.** Skills that pass under one pressure fail under combinations. Mitigation: always combine at least two pressures for discipline-enforcing skills.
- **Stopping at GREEN.** The first passing test means the skill works for that exact scenario. Refactor is where it becomes robust. Mitigation: run at least two distinct pressure combinations before declaring a skill done.

## References

- `source:superpowers-skill-system` — `writing-skills` skill; RED-GREEN-REFACTOR mapping; pressure type taxonomy.
- `wiki:mandatory-skill-invocation` — anti-rationalization tables are populated from baseline testing.
- `wiki:skill-cso-description-trap` — description content is also testable: does the description alone produce correct behavior?
