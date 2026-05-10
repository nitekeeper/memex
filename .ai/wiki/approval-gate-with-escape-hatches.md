---
id: memex:wiki:approval-gate-with-escape-hatches
slug: approval-gate-with-escape-hatches
title: Approval gates have escape hatches, not holes
status: approved
tags: [approval-gate, write-guard, escape-hatches, user-control]
sources: [source:second-brain-blueprint]
related: [memex:wiki:inbox-raw-wiki-pipeline]
proposed-in: session:2026-05-09
approved-in: session:2026-05-09
created: 2026-05-09
updated: 2026-05-09
---

# Approval gates have escape hatches, not holes

Before any wiki write, the agent shows a plan and cost estimate and waits for approval. Escape hatches — trusted shorthand commands that bypass the interactive gate — are allowed, but each has its own built-in safeguard. The gate is never simply removed; it is replaced with a narrower gate.

## Why it matters

Unguarded writes are the primary failure mode in AI-maintained knowledge systems. Without a gate, the agent accumulates drift, duplication, and low-confidence content that is hard to detect and expensive to clean up. The approval gate is the user's control surface over what enters the wiki.

## The pattern

1. **Gate:** agent proposes a write (what, where, estimated token cost) and waits for explicit approval before touching any file.
2. **Escape hatch:** a named command (e.g. `!! wrap`, `!! ready`) that the user issues when they trust the operation enough to skip the interactive prompt.
3. **Hatch safeguard:** the escape hatch is not a blank check — it runs a fixed, documented procedure with its own checks (e.g. hash-check for deduplication, scope limits, dry-run output).

## How to apply in Memex

- The `capture` skill shows a plan before writing any wiki page: title, target path, estimated size, sources it draws from.
- Batch capture (multiple pages in one pass) still gates at the batch level — the agent lists all proposed writes before any file is touched.
- A trusted escape hatch (exact form TBD at synthesis) bypasses the per-page prompt but runs a deduplication check and shows a dry-run diff before committing.
- The gate is not optional for first-time writes to a given path.

## Failure modes

- **Gate fatigue.** Approving everything reflexively defeats the purpose. Mitigation: keep the plan summary short and scannable; the user should be able to reject in two seconds.
- **Escape hatch scope creep.** The hatch gradually expands to cover more cases until the gate is effectively gone. Mitigation: each hatch is documented with an explicit scope; expansion requires a deliberate decision, not drift.
- **Missing token estimate.** User approves without understanding cost. Mitigation: token estimate is a required field in every gate prompt, not optional.

## References

- `source:second-brain-blueprint` — approval-before-write pattern; `!! wrap` / `!! ready` escape hatches with hash-check deduplication.
- `wiki:inbox-raw-wiki-pipeline` — the gate applies at the wiki-write stage of the pipeline.
