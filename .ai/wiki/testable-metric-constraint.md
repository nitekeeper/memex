---
id: memex:wiki:testable-metric-constraint
slug: testable-metric-constraint
title: The self-improvement loop is bounded by what is measurable
synced-at-commit: 4465f3727246b47b71aab3a8255369b0493c0be9
describes-files: []
status: approved
tags: [self-improvement, loop, measurement, design-principles]
related: [memex:wiki:memex-disk-layer, memex:wiki:design-for-async-agents]
created: 2026-05-09
updated: 2026-05-09
---

# The self-improvement loop is bounded by what is measurable

## Summary

Karpathy's AutoResearch insight: "any metric you care about that is reasonably efficient to evaluate can be autoresearched." The inverse also holds — if you can't evaluate it efficiently, you can't improve it automatically. Staleness is Memex's v0 metric: it is computable exactly by diffing `describes-files` against `synced-at-commit`. Accuracy (is the page correct?) and completeness (does the page cover everything relevant?) are not computable in v0. Design the capture/sync/review loop around what is measurable; don't pretend to optimize what isn't.

## Details

In v0, Memex can measure one thing automatically: **staleness**. A page is stale if any file in `describes-files` changed after `synced-at-commit`. This is a git diff — exact, cheap, reliable.

What Memex cannot measure automatically in v0:
- **Accuracy** — is the page's content still correct? Requires reading and reasoning about the code.
- **Completeness** — does the page cover everything relevant? Requires knowing what "relevant" means.
- **Quality** — is the page well-written and useful? Entirely subjective.

The implication: the v0 self-improvement loop should be scoped to staleness detection + human review. The human review step handles accuracy and completeness; the machine handles staleness detection. Do not automate the human's judgment; do automate the signal that triggers it.

Future versions may improve on this — for example, an LLM can read a stale page and the diff and propose a corrected version. But that is a v1+ capability. Do not design v0 around it.

## Pointers

- `sources/analyzed/2026-05-09-karpathy-autoresearch.md` — source of the testable-metric insight
- `sources/analyzed/2026-05-09-karpathy-llm-os.md` — self-improvement as first-class LLM OS capability

## Open questions

- Can an LLM reliably flag its own accuracy errors on a stale page? If so, the human review step could be guided (LLM drafts correction, human approves). That changes the loop design significantly.
- Is there a proxy metric for completeness that doesn't require semantic understanding? e.g., "describes-files has N files but page only mentions M of them" — crude, but computable.
