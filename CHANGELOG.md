# Changelog — Memex

All releases are logged here. Unreleased in-progress work is tracked in `ROADMAP.md`.

Format: [version] — date — summary.

---

## Unreleased

---

## v0.2.0 — 2026-05-11

**upgrade skill**
- New skill: `skills/upgrade/` — upgrades Memex within a consumer product. Reads `memex_path`
  and `memex_dir` from `CLAUDE.md`, checks git tags for new versions, shows changelog excerpt,
  approval gate, git checkout, copies full `dist/`, runs schema migrations, rebuilds DB.
- 10 structural tests passing (95 total).

**Phase 1 — Session-start queue-processing pass**
- `CLAUDE.md` updated: Claude now runs `review-lessons` → `propose-wiki-entry` → `sync` automatically at session start, before the first user message, and shows a summary. No approval gates. Deferred and discarded items are handled silently; only uncertain lessons are left as drafts for the next collaborative session.

**Phase 2 — Self-improve skill**
- New skill: `skills/self-improve/` — unified entry point for running the self-improvement loop solo (autonomous, no gates) or collaboratively (user and Claude work through it together with approval at every step).
- Solo mode: sweeps the conversation for lesson candidates, filters by confidence/contradiction/philosophy signals, writes confident candidates to `lessons/inbox/`, holds uncertain items with `held-for-review: true` + `held-reason` frontmatter, runs review and propose autonomously, shows a summary.
- Collaborative mode: user chooses full loop (capture → review → propose) or queue review only; all existing skill gates intact.
- Updated skill: `skills/review-lessons/` — held items (lessons with `held-for-review: true`) now surface first in the review queue, with `[HELD: <reason>]` markers in the candidate list and review block, and a `Held reason:` display line. Promoting a held lesson clears the held fields; discard/defer leaves them untouched.
- 13 new tests (85 passing total).

---

## v0.1.0 — 2026-05-10

First release. Dogfood-validated against Skill Atelier (19 pages indexed, `rebuild.py` clean).

**Skills shipped:**
- `capture` — write or update wiki entries, on-demand and session-end modes, approval gate
- `sync` — staleness detection via `synced-at-commit` + `describes-files`
- `ask` — FTS5-powered tiered knowledge retrieval (memex → web → model)
- `capture-lesson` — lesson capture, inbox/feedback stream routing
- `review-lessons` — lesson review loop (promote / discard / defer), feedback-first priority
- `propose-wiki-entry` — converts promoted lessons into wiki entries
- `review-wiki` — curation pass (approve drafts, archive stale entries)

**Scripts:** `rebuild.py` (13 tests), `sync.py` (8 tests), `search.py` (11 tests)

**Format specs:** `WIKI_PAGE_FORMAT.md`, `LESSON_FORMAT.md`, `MEMEX_SPEC.md`

**Total tests:** 72 passing.
