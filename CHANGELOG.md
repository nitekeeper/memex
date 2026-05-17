# Changelog — Memex

All releases are logged here. Unreleased in-progress work is tracked in `ROADMAP.md`.

Format: [version] — date — summary.

---

## Unreleased

(no in-progress work)

---

## v2.2.2 — 2026-05-17

**Release-pipeline fix. No code or behavior changes.**

v2.2.1 surfaced a GitHub Actions chaining gap: workflows triggered by
`GITHUB_TOKEN` cannot trigger other workflows (anti-loop guard). The old
`notify-agora.yml` listened for `release: published`, but `release.yml`
creates that release using `GITHUB_TOKEN`, so the event never reached
`notify-agora.yml` and agora was never notified.

Fix: folded the dispatch step into `release.yml` directly. The same
workflow that publishes the GitHub Release now also fires
`repository_dispatch` at agora, using `AGORA_DISPATCH_TOKEN`. No
cross-workflow chaining needed. Deleted `notify-agora.yml`.

End-to-end push-loop is now exercised by this release.

---

## v2.2.1 — 2026-05-16

**Release-tooling validation. No code or behavior changes.**

Exercises the full v2.2.0 release toolchain end-to-end:

- `scripts/bump.py` driving the version-file updates and dist rebuild.
- `.github/workflows/release.yml` building and publishing the GitHub
  Release from a tag push.
- `.github/workflows/notify-agora.yml` firing a `repository_dispatch` at
  `nitekeeper/agora` so the marketplace can auto-bump the pinned version
  without manual intervention.

If you installed v2.2.0 you can stay on v2.2.0 — nothing about Memex's
behavior changed. v2.2.1 exists solely to validate that the release
pipeline works.

---

## v2.2.0 — 2026-05-16

**Caller-built classification for consumer writes (Atelier-style fast path).**

- **`memex:index:write` accepts an optional `librarian_output`.** When a
  consumer (Atelier `tasks` / `decisions` / `meetings`, or any future
  structured-row writer) already knows the document's `domain`, can build
  `searchable` deterministically from the row, and has explicit relations
  in its data model, it passes a Python-built `librarian_output` dict and
  the Librarian subagent dispatch is skipped. Steps 1–3 of the recipe
  (build prompt, dispatch, parse) collapse to a single
  `librarian.validate_output()` call. Persistence still flows through
  `librarian.write_entry()`, so the Index↔target-store coupling and Data
  Steward orphan-detection contracts are unchanged. See
  [memex#1](https://github.com/nitekeeper/memex/pull/1).
- **New helper `librarian.validate_output(obj)`.** Single source of truth
  for the `librarian_output` schema (`index_id`, `key`, `domain`,
  `searchable` required; `metadata` / `relations` optional with defaults).
  Both `parse_response()` (subagent path) and `write_entry()`
  (persistence) now route through it.
- **Spec amended.** New §6.3 *Caller-built classification (consumer fast
  path)* documents the dual-mode contract alongside the original
  LLM-mediated flow. Architectural invariant unchanged: every write is
  mediated by the Librarian write surface; what varies is whether the
  classification step is LLM-mediated or caller-supplied.
- **Reserve the subagent path for prose ingest** (Brain `ingest`,
  transcripts, free-form notes) where `domain` and `relations` need to be
  extracted from text.
- 244 tests passing (was 238 in v2.1.0; 6 new tests cover the
  caller-built path).

**Release-process cleanup (ships with v2.2.0, not user-facing behavior):**

- **Version drift surface reduced from 7 files to 2.** Only
  `.claude-plugin/plugin.json` and `pyproject.toml` now hold the version.
  `tests/test_version.py` was rewritten as a true drift test (asserts the
  two manifests agree; no constant to update). `README.md` and
  `USER_GUIDE.md` now link to the latest dist directory and GitHub
  Releases instead of hard-coding the version.
- **New `scripts/bump.py`.** One command — `python -m scripts.bump
  X.Y.Z` — updates `plugin.json` (version field + the inline `v<X.Y.Z>`
  token in the description), `pyproject.toml`, removes the previous
  `dist/v*/manifest.json`, and rebuilds the new one via
  `scripts.release.build()`. Refuses downgrades and same-version no-ops.
- **New `.github/workflows/release.yml`.** Tag-triggered: push
  `v<X.Y.Z>` and the workflow runs tests, sanity-checks that the
  manifests agree with the tag, builds the dist bundle, extracts the
  matching CHANGELOG section, and creates a GitHub Release with the
  zipped bundle attached. Releases stay deliberate (no merge-to-release
  automation); the tag push is the "I really mean it" signal.
- 253 tests passing after the cleanup (9 new tests cover
  `scripts.bump`).

---

## v2.1.0 — 2026-05-16

**Embeddings: full hybrid-retrieval plumbing (#2 blocker resolved).**

- **Documentation pass** — `USER_GUIDE.md` and the INSTALL.md template
  now have explicit "Embeddings & retrieval" sections covering provider
  selection (`openai` / `voyage` / `local`), required env vars, the
  no-provider FTS5-only fallback, and when to backfill / re-embed.
- **Real Voyage + Local providers.** The previous NotImplementedError
  stubs in `scripts/embeddings.py` are gone. Voyage uses the `voyageai`
  SDK with `VOYAGE_API_KEY` (default model `voyage-3`, 1024-dim). Local
  uses `sentence-transformers` with no API key (default
  `all-MiniLM-L6-v2`, 384-dim; first call downloads ~80MB model
  weights). Both SDKs are lazy-imported — installing memex doesn't
  require either.
- **Per-provider model overrides** — `MEMEX_OPENAI_MODEL`,
  `MEMEX_VOYAGE_MODEL`, `MEMEX_LOCAL_MODEL` env vars let you switch
  models within a provider without code changes.
- **`memex:embed:backfill`** — fills `embedding=NULL` rows with the
  current provider. Idempotent — non-NULL rows untouched. Use after
  configuring a key for the first time, or after FTS5-only ingest.
- **`memex:embed:reembed`** — regenerates ALL embeddings after a
  deliberate provider/model change. Gated by confirmation (destructive
  — overwrites existing embeddings). Reports `previous_recorded`
  alongside the new model so the user can verify what they're replacing.
- **Model-change detection** — `embeddings.detect_model_change()`
  compares the active provider/model against what `registry.json:__embedding_model__`
  recorded the last time `encode()` ran. The reembed skill warns when
  drift is detected (or asks for confirmation when there is none).
- New helpers: `embeddings.active_model_info()` (no API call required)
  and `embeddings.recorded_model_info()` (reads from registry.json).

Test count: 238 passed, 0 skipped (was 211 pre-#2 work; +27 new
embedding tests covering all three providers, backfill, reembed, and
drift detection).

---

## v2.0.0 — 2026-05-16

**Major redesign.** Memex is no longer a project-scoped wiki. It is now a
personal knowledge runtime and shared memory plane for the agent fleet.

### Breaking changes

- `.ai/memex.db` is no longer used. v2 lives at `~/.memex/` (machine-global).
- v1 wiki content is NOT auto-migrated. v1 `.ai/` is archived to
  `~/.memex/legacy/v1-wiki/` on first v2 install (if `MEMEX_V1_PATH` is set).
  Re-ingest manually via `memex:brain:ingest`.
- Self-improvement loop skills (`capture-lesson`, `review-lessons`,
  `propose-wiki-entry`, `review-wiki`) are dropped from Brain. Lessons-as-a-
  consumer is a future project.
- `synced-at-commit` git-anchored staleness is no longer load-bearing. It can
  return as a consumer-specific column if needed.

### Added

- **Three-layer architecture:** Memex Brain (5 skills) / Memex Index +
  5 internal agents / Memex Core (10 CRUD skills).
- **Five Memex-internal agents:** Librarian (Dr. Lakshmi Iyer-Ranganathan),
  Reference Librarian (Dr. Eleanor Whitfield), Archivist (Dr. Heinrich
  Mühlbauer), Database Administrator (Dr. Rajesh Subramanian), Data
  Steward (Dr. Ingrid Bergström).
- **Federated Index** (`~/.memex/index.db`): documents + relations + FTS5 +
  embeddings. Mandatory write-path gateway via the Librarian.
- **Hybrid retrieval** (FTS5 + vector cosine) via Reference Librarian.
  OpenAI `text-embedding-3-small` default; pluggable provider.
- **Content-addressable raw archive** (`~/.memex/raw/`) via Archivist.
- **Multi-store substrate.** Core hosts arbitrary SQLite stores from
  consumer-supplied SQL migrations. Atelier and any future consumer share
  the substrate.
- **24 internal procedures** spanning `memex:core:*`, `memex:index:*`,
  `memex:brain:*`, `memex:steward:*`, `memex:dba:*` — all reached via
  `memex:run`'s routing table (see "Single-skill registration model"
  below).
- **Single-skill registration model.** Only `memex:run` is registered
  in `plugin.json`. All 24 operations live as internal procedures
  (`internal/<category>/<name>/SKILL.md`) discovered through
  `memex:run`'s routing table. This avoids Claude Code's 1%
  skill-description budget truncation.
- **Eventually consistent** atomicity contract between Index and target
  stores; Data Steward reconciles orphans via audit.

### Changed

- Storage model is SQLite-first. Markdown is a derived export view.
- Cold-start cost reduced significantly: no ops-file routing, no `hot.md`,
  no response-footer compliance tax.
- Plugin remains a Claude Code custom plugin, globally accessible from any
  session regardless of working directory.

### Removed

- Obsidian integration. Memex v2 is Claude Code-native.
- Web-Clipper-driven ingestion. `memex:brain:ingest` accepts payloads
  directly (URL, body, or both).
- The `!! command` syntax. Skills are invoked through Claude Code's
  standard skill mechanism.

---

## v0.2.1 — 2026-05-11

**docs**
- `USER_GUIDE.md` restored to source root — was present in v0.1.0 dist but never tracked in source, causing it to be dropped from v0.2.0 dist. Updated for v0.2.0 (9 skills, consumer install pattern, self-improve + upgrade docs).


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
