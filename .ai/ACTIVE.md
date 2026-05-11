---
id: memex:wiki:active
slug: active
title: Memex — current focus
describes-files: ["ROADMAP.md", "GOALS.md"]
status: draft
tags: [product, active]
created: 2026-05-09
updated: 2026-05-11
---

# Current focus

**`upgrade` skill shipped 2026-05-11.** Consumer-side upgrade skill bundled in products. `self-improve` skill + session-start queue-processing also complete (unreleased). 95 tests passing. Ready for v0.2 release.

## Next

1. **Cut v0.2 release** — includes `self-improve`, session-start queue pass, and `upgrade` skill. ~3 new skills since v0.1.0.
2. **skill-atelier consumer setup** — first real consumer of the `upgrade` skill; bundle Memex `dist/` into skill-atelier, declare `memex_path` + `memex_dir`.

## Completed (since v0.1.0)

- `self-improve` skill — 2026-05-11 (13 tests)
- Session-start queue-processing pass (Phase 1) — 2026-05-11
- `upgrade` skill — 2026-05-11 (10 tests)

## Completed (v0.1.0)

- Format & schema lock — 2026-05-09
- Rebuild script — 2026-05-09
- 7 skills (capture, sync, ask, capture-lesson, review-lessons, propose-wiki-entry, review-wiki) — 2026-05-10
- Dogfood replacement — 2026-05-10
- v0.1.0 release — 2026-05-10

## Open items

- v0.2 release not yet cut
- 3 quality follow-ups from rebuild code review (non-blocking)
