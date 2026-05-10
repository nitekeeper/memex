---
id: memex:wiki:active
slug: active
title: Memex — current focus
synced-at-commit: ef4067c
describes-files: ["ROADMAP.md", "GOALS.md"]
status: draft
tags: [product, active]
created: 2026-05-09
updated: 2026-05-10
---

# Current focus

**`capture-lesson` skill v0 shipped 2026-05-10.** `skills/capture-lesson/SKILL.md` + `REFERENCE.md` + `docs/LESSON_FORMAT.md`. On-demand + session-end modes, inbox/feedback stream routing. 10 tests passing. First skill in the self-improvement loop. Next is `review-lessons` v0.

## Next

1. **`review-lessons` skill v0** — lesson review, promotion to wiki/methodology, discard. Next in self-improvement loop.
2. **`docs/MEMEX_SPEC.md`** — short spec of what Memex is, does, and doesn't do.

## Completed

- Format & schema lock — 2026-05-09
- Rebuild script — 2026-05-09 (13 tests, CLI, smoke tested)
- Capture skill v0 — 2026-05-10
- Sync skill v0 — 2026-05-10 (SKILL.md + REFERENCE.md + sync.py, 8 tests)
- Ask skill v0 — 2026-05-10 (SKILL.md + REFERENCE.md + search.py, 11 tests)
- Capture-lesson skill v0 — 2026-05-10 (SKILL.md + REFERENCE.md + LESSON_FORMAT.md, 10 tests)

## Open items

- `docs/MEMEX_SPEC.md` not yet written
- 3 quality follow-ups from rebuild code review (non-blocking): surface dropped links as warnings; friendlier error on duplicate id; decide policy for created/updated defaults

## Pointer

If this entry is stale, compare `synced-at-commit` to repo HEAD; check whether `describes-files` have changed.
