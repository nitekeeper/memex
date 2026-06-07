-- code_graph.db: a SEPARATE, self-contained store for the code-navigation graph
-- (v2.9.0). NOT part of index.db — it holds NO authoritative knowledge content
-- and carries no FK into index.db's `documents`. The EXTRACTOR is external
-- (graphify, AST-only, run by the consumer with `graphify update <path>
-- --no-cluster`); memex is only the STORE + bounded-QUERY layer.
--
-- Keyed by repo IDENTITY (owner/repo string), never clone path — so the store
-- survives ephemeral clones and repo moves across machines (WSL + macOS).
--
-- Every statement is re-entrant (`... IF NOT EXISTS`); applying this file twice
-- is a no-op for pre-existing objects (the install additive-reapply path relies
-- on this).
--
-- Edge → node FK design (see scripts/code_graph.py docstring for the full
-- rationale): each edge carries a composite FK on (repo, source) → nodes only.
-- The (repo, target) endpoint is INTENTIONALLY NOT a FK. graphify ingests
-- file-by-file fragments, and a cross-file edge's target node may be owned by a
-- file that has not been ingested yet within the same full-graph pass; a target
-- FK would make fragment ordering brittle. Target integrity is instead enforced
-- by `prune_dangling_edges()` (the dangling-edge sweep) + `invalidate_file()`'s
-- explicit inbound-edge deletion. Cascade-on-node-delete correctness — the
-- priority — is preserved: deleting a file's source nodes cascades away the
-- edges that file owns (FK on source), and inbound edges to its symbols are
-- swept explicitly. ON DELETE CASCADE is active because get_connection sets
-- `PRAGMA foreign_keys = ON`.

CREATE TABLE IF NOT EXISTS repos (
    repo            TEXT PRIMARY KEY,        -- owner/repo identity (not a path)
    built_at_commit TEXT,                    -- commit the graph was built from (freshness)
    needs_update    INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT NOT NULL,
    schema_version  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS nodes (
    repo            TEXT NOT NULL,
    id              TEXT NOT NULL,           -- graphify content-derived stable id (verbatim)
    label           TEXT,
    file_type       TEXT,
    source_file     TEXT,
    source_location TEXT,
    PRIMARY KEY (repo, id),
    FOREIGN KEY (repo) REFERENCES repos(repo) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS edges (
    repo             TEXT NOT NULL,
    source           TEXT NOT NULL,
    target           TEXT NOT NULL,
    relation         TEXT NOT NULL,
    confidence       TEXT,
    confidence_score REAL,
    weight           REAL,
    source_file      TEXT,
    source_location  TEXT,
    context          TEXT,
    PRIMARY KEY (repo, source, target, relation),
    FOREIGN KEY (repo, source) REFERENCES nodes(repo, id) ON DELETE CASCADE
);

-- callers(node): edges WHERE target=? AND relation='calls'.
CREATE INDEX IF NOT EXISTS idx_cg_edges_target  ON edges(repo, target, relation);
-- dependencies(node): outbound edges WHERE source=? AND relation IN (...).
CREATE INDEX IF NOT EXISTS idx_cg_edges_source  ON edges(repo, source, relation);
-- fragment invalidation: nodes/edges owned by one source_file.
CREATE INDEX IF NOT EXISTS idx_cg_nodes_srcfile ON nodes(repo, source_file);
CREATE INDEX IF NOT EXISTS idx_cg_edges_srcfile ON edges(repo, source_file);
-- where_is(name): label lookup.
CREATE INDEX IF NOT EXISTS idx_cg_nodes_label   ON nodes(repo, label);
