---
id: memex:wiki:active
slug: active
title: Memex — current focus
synced-at-commit: 9c00b19711d6147c318e47054217b65c506e60ce
describes-files: ["ROADMAP.md", "GOALS.md"]
status: draft
tags: [product, active]
created: 2026-05-09
updated: 2026-05-10
---

# Current focus

**Sync skill v0 complete 2026-05-10.** `skills/sync/SKILL.md` + `REFERENCE.md` + `scripts/sync.py` shipped. Staleness detection via `synced-at-commit` + `describes-files`. Fast-forward / conflict gate workflow. 8 tests passing. Next is the `search` skill v0.

## Next

1. **`search` skill v0** — FTS5-powered search across project wiki pages.

2. **`docs/MEMEX_SPEC.md`** — short spec of what Memex is, does, and doesn't do. Can be written before v0.1 release.

## Completed

- Format & schema lock — 2026-05-09
- Rebuild script — 2026-05-09 (13 tests, CLI, smoke tested)
- Capture skill v0 — 2026-05-10 (SKILL.md + REFERENCE.md, 4 tests)
- Sync skill v0 — 2026-05-10 (SKILL.md + REFERENCE.md + sync.py, 8 tests)

## Open items

- `docs/MEMEX_SPEC.md` not yet written
- 3 quality follow-ups from rebuild code review (non-blocking): surface dropped links as warnings; friendlier error on duplicate id; decide policy for created/updated defaults
- 4 capture SKILL.md follow-ups (non-blocking): tighten "intervenes" definition in approve-all; align session-end skip phrasing with on-demand skip phrasing; add mid-batch validation failure rollback policy to error table; add explicit project-root confirmation to step 1

## Pointer

If this entry is stale, compare `synced-at-commit` to repo HEAD; check whether `describes-files` have changed.
