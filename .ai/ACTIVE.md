---
id: memex:wiki:active
slug: active
title: Memex — current focus
synced-at-commit: 87441ab80003822059da407cd898c9322d2ea078
describes-files: ["ROADMAP.md", "GOALS.md"]
status: draft
tags: [product, active]
created: 2026-05-09
updated: 2026-05-09
---

# Current focus

**Synthesis + rebuild script complete 2026-05-09.** Format spec locked (`docs/WIKI_PAGE_FORMAT.md`), schema locked (`db/schema.sql`), rebuild script shipped (`scripts/rebuild.py`, 13 tests, CLI). Next session is the `capture` skill v0.

## Next

1. **`capture` skill v0** — AI skill that writes/updates a project-wiki page. Brainstorm → plan → implement. Inputs: `docs/WIKI_PAGE_FORMAT.md` (format contract), `scripts/rebuild.py` (validates output). Follow `wiki:skill-file-structure` + `wiki:progressive-disclosure-in-skills` + `wiki:tdd-for-skill-authoring`.

2. **`docs/MEMEX_SPEC.md`** — short spec of what Memex is, does, and doesn't do. Can be written in parallel with capture skill or just before v0.1 release.

## Completed this session (2026-05-09)

- Format & schema lock — single page format, minimal core + extensible, 3-state status (`draft`/`approved`/`archived`), normalized join tables (`links`, `page_files`, `page_tags`), one DB per project co-located at `.ai/memex.db`
- Rebuild script — 6-task TDD implementation, 13 tests, WAL safety, two-pass FK strategy, FTS5, CLI. Smoke tested: indexed 13 real pages from `.ai/wiki/`, 47 tags, 12 links.
- Renamed branch `master` → `main`

## Open items

- `docs/MEMEX_SPEC.md` not yet written
- Research session notes (sessions 2–4: Karpathy, second-brain, Superpowers) not captured as individual session files — framework sessions/notes/ only has first design session + synthesis session
- 3 quality follow-ups from code review (non-blocking): surface dropped links from INSERT OR IGNORE as warnings; friendlier error on duplicate id; decide policy for created/updated defaults

## Pointer

If this entry is stale, compare `synced-at-commit` to repo HEAD; check whether `describes-files` have changed.
