---
id: memex:wiki:active
slug: active
title: Memex — current focus
describes-files: ["ROADMAP.md", "GOALS.md"]
status: draft
tags: [product, active]
created: 2026-05-09
updated: 2026-05-10
---

# Current focus

**v0.1.0 released 2026-05-10.** 7 skills, 3 scripts, 72 tests, dogfood-validated. Tagged `v0.1.0`. `dist/` cut with MANIFEST.md + all skill files + format specs + scripts + schema.

## Next (v0.2 planning)

1. **Release tooling skill** — `meta:cut-release` equivalent for Memex. Currently dist/ is built by hand.
2. **`docs/MEMEX_SPEC.md` follow-up** — spec written for v0.1 but not yet used as a gate for new features.
3. **3 quality follow-ups** (non-blocking): surface dropped links as warnings; friendlier error on duplicate id; created/updated defaults policy.
4. **Embedding-based search** — sqlite-vec upgrade path noted in schema comments. Candidate for v0.2.

## Completed (v0.1.0)

- Format & schema lock — 2026-05-09
- Rebuild script — 2026-05-09 (13 tests)
- `capture` skill v0 — 2026-05-10
- `sync` skill v0 — 2026-05-10 (8 tests)
- `ask` skill v0 — 2026-05-10 (11 tests)
- `capture-lesson` skill v0 — 2026-05-10 (10 tests)
- `review-lessons` skill v0 — 2026-05-10 (10 tests)
- `propose-wiki-entry` skill v0 — 2026-05-10 (8 tests)
- `review-wiki` skill v0 — 2026-05-10 (8 tests)
- Dogfood replacement — 2026-05-10 (19 pages indexed in Skill Atelier)
- v0.1.0 release — 2026-05-10

## Open items

- 3 quality follow-ups from rebuild code review (non-blocking)
- No release tooling skill yet (dist/ built manually for v0.1)

## Pointer

If this entry is stale, compare HEAD to when `describes-files` last changed; run `sync` to update `synced-at-commit`.
