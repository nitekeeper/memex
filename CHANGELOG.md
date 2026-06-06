# Changelog — Memex

All releases are logged here. Unreleased in-progress work is tracked in `ROADMAP.md`.

Format: [version] — date — summary.

Note: historical references to `docs/plans/`, `docs/specs/`, `docs/superpowers/` in entries below are recoverable via git history; the directories were untracked in memex#22.

---

## Unreleased

(no in-progress work)

---

## v2.7.0 — 2026-06-06

### Added — GraphRAG knowledge layer

Applies Microsoft GraphRAG's recipe (build a graph → cluster hierarchically →
summarize bottom-up → answer global via map-reduce / local via neighborhood
expansion) over the federated Index as **derived** artifacts. Document writes
still flow through the Librarian (spec §6); the community layer summarizes
already-indexed documents and is never a document-ingest path.

- **Schema (`db/index.sql`, re-entrant additive).** New tables `communities`,
  `community_members` (MECE per level), `community_reports` (+ summary
  embedding). `install.run()` re-applies `index.sql` on existing index.db so
  the layer lands without a separate migration file.
- **Graph population (`scripts/graph_build.py`).** Deterministic, LLM-free
  k-NN over document embeddings → `relations` rows with a distinct
  `rel_type='similar_to'` (`confidence`=cosine), kept separate from
  Librarian-authored semantic edges. The relation graph is empty on a fresh
  Brain, so this seeding step is load-bearing. Env: `MEMEX_GRAPH_KNN_K` (5),
  `MEMEX_GRAPH_SIM_THRESHOLD` (0.5).
- **Hierarchical community detection (`scripts/communities.py`).** Pure-stdlib
  greedy-modularity clustering with a fixed tie-break (deterministic),
  recursing inside oversized communities for hierarchical levels. No new
  dependency. Env: `MEMEX_COMMUNITY_SIZE_CAP` (10).
- **Bottom-up community reports (`scripts/agents/community_reporter.py` +
  `prompts/community_reporter.md` + `internal/brain/community-report/`).**
  Option-B subagent flow; one LLM call per community; lazy/incremental;
  EmbeddingUnavailable-tolerant.
- **Ask modes (`scripts/brain.py`, `internal/brain/ask/`).** `flat` (default,
  unchanged), `global` (map-reduce over `community_reports`), `local`
  (cosine-seed + relation-neighborhood + attached reports).
- **Maintenance entry point (`internal/brain/graph-rebuild/`).** Operator
  recipe: build graph → detect communities → generate missing reports.

Deferred (follow-ups): DRIFT search, LLM-confirmed semantic relations, a
within-document entity layer.

### Migration

Additive, backward-compatible. `install.run()` re-applies the re-entrant
`db/index.sql` to materialize the new tables on existing installs; no data
migration. `memex:run ask` defaults to `flat` mode — existing behavior is
unchanged. New `relations.rel_type='similar_to'` edges and all community
tables are rebuildable at any time via `memex:brain:graph-rebuild`.

---

## v2.6.2 — 2026-06-02

### Fixed

- **`memex:run ask` crashed on hyphenated queries (FTS5 `MATCH`).** `reference_librarian.execute_query_plan` passed the planner's `fts_query` to `documents_fts MATCH ?` unescaped; a bare hyphenated term — most commonly a capture slug like `memex22-superpower-2026-05-10-sync-skill` — was parsed by FTS5 as operator/column-filter syntax and raised `sqlite3.OperationalError` ("no such column: …") before any matching. The `MATCH` is now retried once with the query escaped as a single double-quoted FTS5 phrase; valid boolean queries (`OR`/`AND`/`NOT`, quoted phrases, prefix `*`) parse on the first try and are unaffected. Surfaced by the memex#22 dogfood-capture follow-up (#27) — a literal `ask <slug>` was the only query shape that exposed it. Adds `tests/test_reference_librarian_hyphen_query.py` (PR #29).

### Migration

(none — backward-compatible bug fix; no schema or API change.)

---

## v2.6.1 — 2026-06-01

### Docs

- **CLAUDE.md portability** — operational charter (M-rules) and per-skill/agent model recommendations folded into `CLAUDE.md` so installers inherit the maintainer's posture without reverse-engineering it (PR #25).
- **Process-artifact untracking (memex#22)** — `docs/specs/`, `docs/plans/`, and `docs/superpowers/` removed from the git tree; Memex itself is now the canonical store (`memex:run capture` writes, `memex:run ask` reads). Historical bodies remain recoverable via git history pre-2026-05-26. Doc references in `skills/run/SKILL.md`, `README.md`, `docs/CORE.md`, `docs/PACKAGING.md`, and the `EmbeddingUnavailable` docstring (`scripts/embeddings.py`) updated to point at git history / `memex:run ask` (PR #26).

### Migration

(none — documentation and repo-housekeeping only; no behavioral code change. Shipped bundle deltas are limited to doc-reference wording in `README.md`, `skills/run/SKILL.md`, and one docstring.)

---

## v2.6.0 — 2026-05-20

### Added

- **Public `ensure_internal_agents(db_path)` API** — idempotent verify-and-seed for any consumer that touches `agents.db` directly (atelier's bootstrap, future plugins, manual restore scripts). Returns `{"status": "already_present" | "repaired", "missing_before": list[str], "present_after": list[str]}`. Raises `InternalAgentsMissingError` if seeding fails. Initialises schema if `db_path` does not exist. Safe to call multiple times. Refs: nitekeeper/atelier#9.

### Fixed

- **`install.run()` was not self-verifying after `_seed_internal`**, and the `_seed_internal` short-circuit was row-blind (matched on `meta.seed_hash` only). If anything wiped the 5 internal Memex agents (`librarian-1`, `reference-librarian-1`, `archivist-1`, `dba-1`, `data-steward-1`) while preserving the `meta` table — e.g. a backup-restore or another consumer rebuilding `agents.db` — `install.run()` would silently no-op. Downstream callers then crashed with `ValueError: Agent not registered: librarian-1`. Now: short-circuit requires both hash-match AND row-presence; `install.run()` ends with `_verify_internal_agents_present()` raising `InternalAgentsMissingError` (listing the specific missing IDs). Refs: nitekeeper/atelier#6 bug #3.

### Internal

- `chore(lint): remove no-op ignores from pyproject.toml` (PR #18).

### Migration

(none — additive API + bug fix; existing surface unchanged. `install.run()`'s new post-condition will catch any pre-existing missing-agent state on the next install invocation.)

---

## v2.5.1 — 2026-05-17

### Fixed

- **`registry.list_stores()` leaked `__embedding_model__` config blob.** Since v2.4.1, `scripts.embeddings._record_model_info()` writes `__embedding_model__` to `registry.json` to track the active provider/model. `list_stores()` returned every value in the file (including this config dict), so downstream consumers iterating registered stores saw a malformed row with no `name` key. The registry API now reserves the `__dunder__` namespace for internal config and filters reserved keys out of all public reads/writes.
- **`get_store("__embedding_model__")` returned the config dict** instead of `None`. Now returns `None`.
- **`register_store("__foo", …)` succeeded** with no namespace protection. Now raises `ValueError` ("reserved namespace").
- **`unregister_store("__embedding_model__")` would have deleted the config blob.** Now a no-op returning `False`.
- **`update_schema_version("__foo", …)` would have rewritten the config blob's value as a string.** Now a no-op returning `None`.

### Migration

No action required. The fix tightens the contract — no legitimate caller was depending on the buggy behavior. Downstream consumers (Atelier's `backend_memex.py`) can now drop client-side `__*` filtering.

---

## v2.5.0 — 2026-05-17

### Added

- **Auto-bootstrap on `memex:run` (Step 0.2).** Detects missing/incomplete `~/.memex/`, prompts strictly `(y/n)`, runs `scripts.install` via Python stdin (deterministic match) on `y`.
- **Python 3.10+ preflight (Step 0.1).** `python3 -c 'sys.version_info[:2] >= (3, 10)'`; fallback to `python` then `py -3`; OS-specific install instructions on miss.
- **`scripts/paths.py`.** Plugin-anchored `PLUGIN_ROOT`, `DB_DIR`, `PROMPTS_DIR`. Import-time bundle integrity check.
- **`~/.memex/config.json`.** Persistent plugin-root cache; written on first invocation, read by all subsequent ones. Eliminates per-invocation discovery.
- **`scripts.db.MemexNotInitializedError` + `require_bootstrap()`.** Typed precondition for direct Python imports.
- **`MemexHomeInvalidError` + `$MEMEX_HOME` / `~/.memex/` validation.** Rejects out-of-home paths and symlinked home unless `MEMEX_HOME_ALLOW_UNUSUAL=1`.
- **v1-archive symlink protection.** `copytree(symlinks=True)`; `$MEMEX_V1_PATH` / `.ai` validation. New `MEMEX_V1_PATH_ALLOW_UNUSUAL=1` escape hatch for test fixtures.
- **Internal agent profile hash-pinning.** Drift detection via `agents.db.meta.seed_hash`.
- **Concurrent install lock.** `os.O_NOFOLLOW` + `flock`/`msvcrt.locking`; new `InstallLockBusyError`.
- **`.gitattributes`** enforcing LF line endings.

### Changed

- **Bundle reads CWD-independent.** Library/agent code reads `agents.sql`, `prompts/*.md`, etc. via `DB_DIR` / `PROMPTS_DIR` from `scripts.paths`, no longer via CWD-relative paths.
- **`db/internal_agents_seed.py` relocated to `scripts/_internal_agents_seed.py`.** Eliminates sibling-package import.
- **All user-facing docs say `python3` and `python3 -m pip`.**
- **Brain `ingest`'s manual-install error pointer removed; `Unknown store: article` reworded to point at Step 0.**
- **Plugin install path docs corrected** from `~/.claude-code/plugins/` to `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`.

### Migration

Existing v2.4.1 installs continue to work without action. The first `memex:run` after upgrade re-runs preflight; on a healthy install it passes silently and writes `~/.memex/config.json` for future invocations.

**Degraded install** (deleted DB files, partial install, stale `MEMEX_HOME`): first `memex:run` after upgrade prompts `(y/n)` to bootstrap. Idempotent.

**`$MEMEX_HOME` outside `$HOME`** (rare): v2.5.0 raises `MemexHomeInvalidError`. Set `MEMEX_HOME_ALLOW_UNUSUAL=1` to retain v2.4.x behavior.

**Manually-edited internal agent profiles** (very rare): on upgrade, `_seed_internal()` detects hash drift and prints a stderr warning before overwriting. Back up before running install if you've customized profiles.

### Spec
- `docs/specs/2026-05-17-install-hardening-design.md` (cycle-3 design); v2-redesign spec now has §8.6 cross-reference.

---

## v2.4.1 — 2026-05-17

### Changed
- Embedding failures now raise a typed `embeddings.EmbeddingUnavailable`
  exception with `reason` / `provider` / `detail` fields, replacing the
  silent broad-`Exception` swallow across every `encode()` call site
  (audit: 6 skill markdown + 2 Python). New helper `embeddings.log_skip()`
  writes structured entries to `~/.memex/audits/embedding-skip-log.md`
  for operator visibility. Reason taxonomy (frozen contract):
  `not_configured` | `oversize_input` | `provider_error` | `unknown`.
- Consumers (Atelier) should narrow their existing `except Exception`
  catches to `except embeddings.EmbeddingUnavailable`. Behavior is
  backwards-compatible — `EmbeddingUnavailable` extends `Exception`.

### Migration
- No action required for upgrade. Existing broad-`Exception` callers
  continue to work. Operators may want to `tail -f
  ~/.memex/audits/embedding-skip-log.md` to surface previously-silent
  embedding failures.

### Spec
- New §6.5 "Embedding failures are typed and audited" in the v2 redesign
  spec; full design at `docs/specs/2026-05-17-embedding-unavailable-design.md`;
  DL-#26 in the Decision Log.

---

## v2.4.0 — 2026-05-17

### Steward — `repair` action + typed `OrphanNotFoundError`

**What.** `memex:steward:reconcile-orphan` gains a fourth action, `repair`,
which backfills `documents.row_id` from a known target PK and writes an
audit row. Targets the forward-orphan class where the Index row exists,
the target row exists, but the `row_id` link was never written. Requires
a new `repair_row_id` kwarg; validates the target store is registered and
that the supplied row exists before updating.

A new typed exception `scripts.agents.data_steward.OrphanNotFoundError`
is raised when `reconcile_orphan()` is called with an unknown `index_id`
(all actions), or when `repair` is called against a row whose `row_id`
is already populated (i.e., not the orphan class `repair` handles). The
exception carries `index_id` and `reason` attributes for catch-by-class
consumers.

`delete-index` now also writes an audit row (previously silent).

**Why.** Negotiated with Atelier as the primitive their v1.1.0 orphan
sweep needs. Without it, consumers would either skip the dangling-link
class entirely or fall back to raw `UPDATE documents SET row_id=?` SQL,
which bypasses the audit trail and the contract that all reconciliation
flows through `memex:steward`. See the Atelier 1.C correspondence
(forwarded 2026-05-17).

**Migration.** Additive. The signature change is a new optional kwarg;
no existing callers break. Existing `delete-index` and `note` callers
should expect `OrphanNotFoundError` instead of silent no-op when the
`index_id` is unknown — this is a behavior tightening, not a regression
(the prior silent no-op masked typo bugs).

### Spec orientation — closed (c) on Atelier 1.C

Atelier proposed adopting cross-store ATTACH-and-atomic transactions in
`librarian.write_entry`. Confirmed not viable under SQLite's WAL +
ATTACH semantics (each attached DB has its own WAL; master-journal
atomicity is rollback-mode only). Decision Log #25 and §6.2 stand.

---

## v2.3.0 — 2026-05-17

### Index — duplicate-key invariant (spec §6.4)

**What.** `documents.key` now carries a UNIQUE index
(`documents_key_unique_idx`), and `librarian.write_entry()` prechecks for
collisions and raises a typed `librarian.DuplicateKeyError` (carrying the
colliding key and existing `index_id`) before INSERT. The schema UNIQUE
constraint remains as last-line defense.

**Why.** Promotes the Librarian's existing "never silently overwrites"
policy from agent-side discipline to a schema-level invariant. Negotiated
with Atelier as defense-in-depth: Atelier's own `key_sequences` allocator
is the primary uniqueness mechanism; UNIQUE(`key`) catches accidental
collisions from any consumer (including future ones).

**Distinction from near-duplicate flagging.** UNIQUE(`key`) is an
exact-match invariant. The Librarian's near-duplicate content-similarity
policy (canonical-form hashing, clustering) remains separate and
complementary — see spec §6.4.

**Migration.** `scripts/install.py` upgrades pre-existing `index.db`
files in place: drops the old non-unique `documents_key_idx`, creates
`documents_key_unique_idx`. If duplicate keys are already present in the
DB, the migration refuses with a `ValueError` listing the offending keys
— operators resolve manually (`memex:steward:reconcile-orphan` or direct
SQL) and re-run install.

**Semantics.** SQLite treats NULLs as distinct in UNIQUE indexes, so
unkeyed captures (key IS NULL) remain unconstrained.

Files: `docs/specs/2026-05-16-memex-v2-redesign-design.md` (§5.2, new §6.4,
§A.1 Librarian role-card), `db/index.sql`, `scripts/install.py`,
`scripts/agents/librarian.py`. Tests: 6 new (`test_index_schema.py`,
`test_librarian_harness.py`, `test_install.py`). 284 passing.

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
