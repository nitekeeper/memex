# Memex Brain (Plan 3)

Brain is Memex's opinionated second-brain layer. It owns `article.db`
and exposes five procedures for daily use.

## Invocation

Per spec §8.0, only `memex:run` is registered as a top-level Claude
Code skill. Brain procedures live at `internal/brain/<name>/SKILL.md`
and are reached on demand via the natural-language intent routing
table inside `skills/run/SKILL.md`. To use Brain, the user expresses
an intent to `memex:run` — e.g. "ingest this article", "ask about X",
"capture a thought" — and `memex:run` reads the matching procedure
file and follows it.

Users do not invoke `memex:brain:*` skills directly; they invoke
`memex:run` with natural-language intent, and the routing table
resolves the intent to the correct Brain procedure file.

## Procedures

| Procedure | Path | Purpose |
|---|---|---|
| memex:brain:ingest | internal/brain/ingest/SKILL.md | Add an external article (with hash-based rerun safety) |
| memex:brain:ask | internal/brain/ask/SKILL.md | Natural-language query, ranked results |
| memex:brain:capture | internal/brain/capture/SKILL.md | Free-form note |
| memex:brain:lint | internal/brain/lint/SKILL.md | Data Steward audit scoped to Brain |
| memex:brain:synthesize | internal/brain/synthesize/SKILL.md | Multi-source synthesis with provenance |
| memex:brain:community-report | internal/brain/community-report/SKILL.md | Bottom-up structured report for one GraphRAG community |
| memex:brain:graph-rebuild | internal/brain/graph-rebuild/SKILL.md | Operator maintenance: build graph -> communities -> reports |

## GraphRAG knowledge layer (v2.7.0)

Memex applies Microsoft GraphRAG's recipe over the federated Index as a set of
**derived** artifacts maintained out-of-band (document writes still flow
through the Librarian — M3 / spec §6; the community layer summarizes already-
indexed documents and is never a document-ingest path).

Pipeline (`internal/brain/graph-rebuild/SKILL.md` is the operator entry point):

1. **Graph population** — `scripts/graph_build.py` connects each embedded
   document to its top-K most-similar neighbors (cosine >= threshold) with a
   distinct `relations.rel_type='similar_to'` edge whose `confidence` is the
   cosine. Deterministic, LLM-free, dependency-light (pure stdlib +
   `embeddings.cosine`). Env: `MEMEX_GRAPH_KNN_K` (5), `MEMEX_GRAPH_SIM_THRESHOLD`
   (0.5). The graph is empty on a fresh Brain, so this seeding step is
   load-bearing — without it the community layer would be inert.
2. **Hierarchical community detection** — `scripts/communities.py` runs
   pure-stdlib greedy-modularity clustering over the weighted relation graph
   and recurses inside communities above a size cap to produce hierarchical
   levels (MECE per level, parent/children). Deterministic (fixed tie-break);
   degrades on an empty graph. Env: `MEMEX_COMMUNITY_SIZE_CAP` (10). Writes
   `communities` + `community_members`.
3. **Bottom-up community reports** — `scripts/agents/community_reporter.py`
   summarizes each community (member text ordered by node degree; child-report
   roll-up substitutes for raw text once a char budget fills) into a structured
   report `{title, summary, rating, findings}` + a summary embedding. One LLM
   call per community; lazy/incremental (only report-less communities).
   Writes `community_reports`.

**Ask modes** (`memex:brain:ask`):
- `flat` (default, unchanged) — FTS5 + vector cosine over `documents`.
- `global` — map-reduce over `community_reports` at a level for corpus-wide /
  thematic questions (`brain.global_ask_prepare` / `parse_map_response` /
  `global_ask_reduce_prepare`).
- `local` — seed by cosine, expand the `relations` neighborhood, attach the
  seeds' community reports (`brain.local_ask`).

Deferred (follow-ups, not in v2.7.0): DRIFT search, LLM-confirmed semantic
relations, a within-document entity layer.

Known limitation (deferred): community detection's recursive balanced-split can,
on a perfectly uniform dense clique, peel into a deep hierarchy of many tiny
communities (one report LLM call each). Not a practical risk — real kNN graphs
are built with out-degree capped at k=5, so they are never uniform cliques. See
the comment in `scripts/communities.py` near the recursion guard.

## Storage

`~/.memex/article.db` with three tables:
- `articles` — external sources, with `source_hash` + `raw_path`
- `captures` — free-form notes
- `syntheses` — generated synthesis documents with `inputs_json` provenance

All routed through the Librarian on write; through the Reference
Librarian on read.

`~/.memex/index.db` additionally holds the derived GraphRAG layer
(`communities`, `community_members`, `community_reports`, plus `similar_to`
edges in `relations`) — rebuilt from `documents` by the graph-rebuild
maintenance path, not written on the document-ingest path.

## Onboarding

First Brain invocation triggers a one-time prompt to register the
human user as an agent. Subsequent invocations skip onboarding.

## Acceptance criteria

1. `pytest tests/` 100% green.
2. `install.run()` creates article.db.
3. First brain.ingest without registered human triggers onboarding.
4. brain.ingest is idempotent on identical content.
5. brain.ask returns results from index.db.
6. brain.synthesize produces a syntheses row with inputs_json provenance.
7. brain.lint generates an audit report.

## What Plan 3 ships beyond what brainstorming committed to

Adds `data_steward.reconcile_orphan` (was deferred from Plan 2). The
`reconcile_orphan` action supports `delete-index`, `repair`, and `note`
resolutions today; `reindex` is reserved for reverse-orphan handling and
raises `NotImplementedError` until Plan 4 re-embedding tooling lands.
`repair` was added in v2.4.0 to backfill link-missing orphans surfaced by
consumer-side sweeps (see Atelier 1.C correspondence).
