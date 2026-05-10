# Design Notes — Memex

Decisions log. Each entry records what was decided, why, and what alternatives were rejected.

---

## 2026-05-09 — Repo scaffolded; research phase begins

**Decision:** Scaffold the Memex repo at `C:\Users\user\Documents\Skills\memex\` as a sibling to `skill-atelier\`. Begin research phase with Karpathy as first source.

**Context:** Decided in Skill Atelier's first design session (2026-05-09). The repo was deferred from that session to keep focus on framework-level decisions. Now created in the second session.

**Structure adopted:**
- Follows Skill Atelier's Foundation Plan Layer 2 shape: own DESIGN_NOTES, ROADMAP, CHANGELOG, GOALS, .ai/, sources/, lessons/, db/, dist/, skills/, tests/.
- No format or schema locked yet — that waits for synthesis after all three research sources are ingested.

**Source ingestion order (inherited from first design session):**
1. Karpathy's writings on self-improvement and LLM-as-OS
2. User's existing LLM wiki build
3. Superpowers (deliberately last)

**Alternatives rejected:**
- Scaffold the full format spec now — rejected. Locking format before research contradicts the "research before design" principle (CLAUDE.md Working Rule 1).
- Use Skill Atelier's repo as a monorepo — rejected. Foundation Plan principle 2: each product is its own repo with its own lifecycle.

---

## 2026-05-09 — Synthesis session; format + schema locked; rebuild script shipped

**Decisions locked:**

| Decision | Choice | Alternatives rejected |
|---|---|---|
| Page types | Single format; `describes-files` optional | Two separate schemas — over-engineering |
| Frontmatter philosophy | Minimal core + extensible | Opinionated-and-complete — framework curation fields not universal |
| Body structure | Free-form markdown | Required sections — too constraining for heterogeneous content |
| Status values | `draft` \| `approved` \| `archived` | 4-state with `deprecated` — rejected (user preference for fewer states) |
| Relationships | `links(from_id, to_id, rel_type)` join table | JSON column — incompatible with Stage 3 graph layer |
| File tracking | `page_files(page_id, file_path)` join table | JSON column — "which pages track this file?" query would be a scan |
| Tags | `page_tags(page_id, tag)` join table | JSON column — inconsistent with other join tables |
| DB location | One DB per project at `.ai/memex.db` | Shared cross-project DB — breaks "wiki travels with project" principle |
| `status` semantics | Curation lifecycle (not staleness state) | Framework stub used `current`/`stale` — conflation removed |

**Conflict resolved:** Framework's `docs/PROJECT_WIKI_FORMAT.md` used `status` for staleness (`current`/`stale`). This was wrong — staleness is computed from `synced-at-commit` vs HEAD, never stored. Fixed in both `PROJECT_WIKI_FORMAT.md` and Memex's `WIKI_PAGE_FORMAT.md`.

**Artifacts produced:**
- `docs/WIKI_PAGE_FORMAT.md` — canonical page format spec
- `db/schema.sql` — SQLite schema with CREATE TABLE, indexes, FTS5
- `scripts/rebuild.py` — rebuild script (13 tests, CLI, smoke tested)
- `docs/superpowers/plans/2026-05-09-rebuild-script.md` — Plan 1 of 3

**References:** `sessions/notes/2026-05-09-memex-synthesis.md` (framework).

---

## 2026-05-09 — Karpathy sources ingested; three key themes extracted

**Decision.** Ingested three Karpathy pieces as separate source files in `sources/analyzed/`:
1. `source:karpathy-software-2-0` — Software 2.0 (2017)
2. `source:karpathy-llm-os` — LLM OS kernel framing (2023)
3. `source:karpathy-autoresearch` — AutoResearch / self-improvement loop (2026)

**Key findings that will shape Memex design:**

1. **Memex is the "disk" in the LLM OS** — not a feature but a structural layer. The context window is RAM; the project wiki is the disk. Pages must be accurate, queryable, and granular enough to be selectively paged in. This validates `synced-at-commit` staleness (accuracy), FTS5 search (queryability), and small-focused-page style (granularity).

2. **The testable metric is the constraint** (AutoResearch insight) — Memex's self-improvement loop is only as good as its measurement signal. Staleness is measurable via git diff against `describes-files`. Accuracy and completeness are not measurable in v0. Design the loop around what is measurable first.

3. **The project wiki is the "Software 2.0 IDE" for project knowledge** (SW 2.0 insight) — Karpathy asked "who will build the SW 2.0 IDE?" for dataset accumulation/curation. Memex is that IDE for the AI's project dataset: capture, detect staleness, surface for review.

4. **Design for teams of agents, not one session** (AutoResearch insight) — "teams of agents collaborating asynchronously" need shared, git-anchored, queryable memory. Memex's design must not assume a single agent or session.

**Derived wiki entry proposals (queued for session close):**
- `wiki:memex-disk-layer` — Memex as the "disk" in the LLM OS; why accuracy/queryability/granularity are the three load-bearing properties
- `wiki:testable-metric-constraint` — The improvement loop is bounded by what is measurable; staleness is v0's metric
- `wiki:design-for-async-agents` — Project wikis serve teams of agents, not single sessions

**References.** `sources/analyzed/2026-05-09-karpathy-software-2-0.md`, `sources/analyzed/2026-05-09-karpathy-llm-os.md`, `sources/analyzed/2026-05-09-karpathy-autoresearch.md`.
