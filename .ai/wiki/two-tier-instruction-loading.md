---
id: memex:wiki:two-tier-instruction-loading
slug: two-tier-instruction-loading
title: Two-tier instruction loading keeps cold-start cost low
status: approved
tags: [architecture, cold-start, token-cost, instruction-loading]
sources: [source:second-brain-blueprint]
related: []
proposed-in: session:2026-05-09
approved-in: session:2026-05-09
created: 2026-05-09
updated: 2026-05-09
---

# Two-tier instruction loading keeps cold-start cost low

Split instruction content into two tiers: a lean root file that loads on every session, and heavier ops files that load only when triggered. The lean file carries identity, routing rules, and invocation triggers — nothing else. Heavy content (session memory, reference docs, ops procedures) defers to skill files or named context files that load on demand.

## Why it matters

Every token in the always-loaded root file costs context on every session, whether or not that content is needed. second-brain-blueprint measured an 86% cold-start token reduction (from ~7,780 to ~1,080 tokens) by moving ops content out of `CLAUDE.md` into deferred files. At scale, this is the difference between a system that fits comfortably in context and one that crowds out working memory.

## How to apply

- Root file (`CLAUDE.md` or equivalent): identity, query-routing rules, pointers to deferred content, invocation triggers. Target ~1,000–2,000 tokens.
- Deferred files: session memory, reference tables, ops procedures, skill bodies. Load only when the session type or user action requires them.
- The trigger mechanism is the skill invocation pattern — a skill body loads when the skill fires, not before.
- If a piece of content is needed on fewer than half of sessions, it belongs in a deferred file.

## Failure modes

- **Creeping root file.** Convenience additions accumulate in the root over time. Mitigation: review root file size at each session close; move anything not needed on every session.
- **Trigger gaps.** Deferred content that never gets triggered is effectively dead. Mitigation: every deferred file has an explicit trigger condition documented in the root file.

## References

- `source:second-brain-blueprint` — cold-start-optimization-design.md, measured 86% reduction.
- `wiki:skill-cso-description-trap` — related: skill descriptions must also avoid carrying workflow content.
