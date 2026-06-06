---
name: memex:brain:graph-rebuild
description: Operator maintenance entry point for the GraphRAG knowledge layer — (re)build the similarity graph over embedded documents, detect hierarchical communities, then generate the missing community reports. Run after a batch of ingests, or whenever the Index has drifted from the derived graph/community/report artifacts.
---

# memex:brain:graph-rebuild

## When to use

The GraphRAG layer (similarity graph -> communities -> community reports) is a
DERIVED set of index artifacts that summarize already-indexed documents. It is
NOT kept live on every write (that would put an LLM call on the write path).
Instead it is rebuilt on demand by this maintenance entry point:

- after a batch of `memex:brain:ingest` / `capture` / `synthesize` writes,
- when `global`/`local` ask returns stale themes,
- on a periodic cadence the operator chooses.

This path NEVER writes documents — document writes go through the Librarian
(M3). It only rewrites the `relations` `similar_to` edges, the `communities` /
`community_members` rows, and the `community_reports` rows.

## Recipe

### Step 1 — Build the similarity graph (deterministic, no LLM)

```python
from scripts import graph_build
g = graph_build.build_graph()   # {"considered", "edges_written", "k", "threshold"}
```

Tunables (env): `MEMEX_GRAPH_KNN_K` (default 5), `MEMEX_GRAPH_SIM_THRESHOLD`
(default 0.5). Idempotent — re-running clears and rewrites the `similar_to`
edges without touching Librarian-authored semantic relations. Degrades on <2
embedded docs (no edges, no crash).

### Step 2 — Detect hierarchical communities (deterministic, no LLM)

```python
from scripts import communities
c = communities.detect_communities()   # {"levels", "communities", "members", "nodes"}
```

Tunable (env): `MEMEX_COMMUNITY_SIZE_CAP` (default 10) — communities larger
than this recurse into deeper levels. Deterministic (fixed tie-break);
degrades on an empty graph (zero communities, no crash).

### Step 3 — Generate the missing community reports (one LLM call each)

Reports are lazy/incremental and built bottom-up (deepest level first so a
parent can roll up its children):

```python
from scripts.agents import community_reporter
for cid in community_reporter.stale_community_ids():   # already deepest-first
    # follow internal/brain/community-report/SKILL.md for each cid:
    #   report_prepare -> dispatch reporter subagent -> parse_report
    #   -> embed summary (tolerate EmbeddingUnavailable) -> report_complete
    ...
```

See `internal/brain/community-report/SKILL.md` for the per-community subagent
dispatch. Only report-less (stale) communities are processed, bounding cost to
one LLM call per new community.

## Notes

- Steps 1-2 are pure Python and can run head-less (no Claude Code session).
  Step 3 needs the session because it dispatches the reporter subagent.
- After a rebuild, `memex:brain:ask` in `global` mode map-reduces over the
  fresh `community_reports`; `local` mode expands the fresh `relations`
  neighborhood and attaches the fresh reports.
