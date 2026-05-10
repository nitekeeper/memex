---
id: memex:wiki:session-snapshot-format
slug: session-snapshot-format
title: Session snapshots are structured, not prose
status: approved
tags: [session-memory, snapshot, cross-session, compression]
sources: [source:second-brain-blueprint]
related: [memex:wiki:two-tier-instruction-loading]
proposed-in: session:2026-05-09
approved-in: session:2026-05-09
created: 2026-05-09
updated: 2026-05-09
---

# Session snapshots are structured, not prose

Cross-session memory is a structured snapshot with fixed fields, not a free-form prose summary. Fixed fields make the snapshot machine-readable, prevent field drift, and make compression deterministic.

## The six fields (from second-brain-blueprint)

| Field | What goes here |
|---|---|
| TASK | What the session was trying to accomplish |
| STATE | What was completed; what is in-flight |
| NEXT | First action the next session should take |
| LOCKED | Decisions that must not be revisited without explicit user intent |
| FILES | Files touched or created this session |
| WATCH | Known risks or open questions to monitor |

Memex's `capture` skill will define its own canonical field set — this is the reference model, not a locked schema.

## Compression by scope exclusion

The compression mechanism is exclusion, not truncation. When a snapshot grows large:

1. Drop items fully resolved and already wiki-ified — the wiki is the record; the snapshot is not.
2. Drop items that are stable and won't change — they belong in a wiki entry or LOCKED.
3. Keep only what the next session needs to act without re-deriving.

Character limits are the wrong lever. A 500-character snapshot with the wrong fields is useless; a 2,000-character snapshot with the right fields is lean.

## Why it matters

Prose summaries drift: each session's author interprets the format differently, fields get dropped, important state gets buried in narrative. Fixed fields force completeness — a NEXT field that is empty is a visible gap, not a hidden omission.

## Failure modes

- **Snapshot as changelog.** Listing everything that happened instead of what the next session needs. Mitigation: write NEXT first; everything else serves NEXT.
- **LOCKED overload.** Treating every decision as locked stiffens the system. Mitigation: LOCKED is for decisions that would cause real damage if silently revisited — not for preferences.
- **Forgetting to exclude wiki-ified content.** Snapshot grows unboundedly. Mitigation: before closing a snapshot, check STATE against the wiki; anything already captured there can be dropped.

## References

- `source:second-brain-blueprint` — wrap-compact-redesign.md (compression via scope exclusion).
- `wiki:two-tier-instruction-loading` — snapshots are deferred content; they load only at session resume.
