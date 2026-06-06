-- index.db: federated metadata + FTS5 + embeddings + cross-store relations.
-- Created via memex:core:create-store with this file as the sole migration.
-- The Librarian (librarian-1) owns writes; Reference Librarian (reference-librarian-1) reads.

CREATE TABLE IF NOT EXISTS documents (
    index_id     TEXT PRIMARY KEY,
    key          TEXT,
    domain       TEXT NOT NULL,
    store        TEXT NOT NULL,
    table_name   TEXT NOT NULL,
    row_id       TEXT NOT NULL,
    searchable   TEXT,
    metadata     TEXT,
    embedding    BLOB,
    created_by   TEXT NOT NULL,            -- FK semantically to agents.db.agents.id; not enforced cross-DB
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX        IF NOT EXISTS documents_domain_idx     ON documents(domain);
CREATE INDEX        IF NOT EXISTS documents_store_idx       ON documents(store);
-- Exact-match uniqueness invariant on `key`. SQLite treats NULLs as distinct,
-- so unkeyed rows remain unconstrained. The Librarian prechecks this index
-- before INSERT and raises a typed DuplicateKeyError on collision; the
-- UNIQUE index is the last-line defense for any code path that bypasses
-- the precheck. See spec §6.4.
CREATE UNIQUE INDEX IF NOT EXISTS documents_key_unique_idx  ON documents(key);

CREATE TABLE IF NOT EXISTS relations (
    from_index_id  TEXT NOT NULL REFERENCES documents(index_id),
    to_index_id    TEXT NOT NULL REFERENCES documents(index_id),
    rel_type       TEXT NOT NULL,
    confidence     REAL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (from_index_id, to_index_id, rel_type)
);

CREATE INDEX IF NOT EXISTS relations_to_idx ON relations(to_index_id);

-- ── GraphRAG community layer (v2.7.0) ─────────────────────────────────────
-- DERIVED index artifacts maintained by the graph/community maintenance path
-- (scripts/graph_build.py + scripts/communities.py + the community-report
-- flow). These are NOT a document-ingest bypass: document writes still go
-- through the Librarian (spec §6). The tables below are rebuilt from
-- `documents` + `relations` and carry no authoritative content of their own.

CREATE TABLE IF NOT EXISTS communities (
    community_id  TEXT PRIMARY KEY,
    level         INTEGER NOT NULL,
    parent        TEXT,                    -- parent community_id (NULL at top level)
    size          INTEGER,                 -- member count at this community's level
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS communities_level_idx  ON communities(level);
CREATE INDEX IF NOT EXISTS communities_parent_idx ON communities(parent);

-- MECE per level: a given index_id appears at most once per level. The PK
-- (community_id, index_id) plus the per-level partitioning enforced by the
-- detector keeps membership mutually exclusive within a level.
CREATE TABLE IF NOT EXISTS community_members (
    community_id  TEXT NOT NULL,
    index_id      TEXT NOT NULL REFERENCES documents(index_id),
    level         INTEGER NOT NULL,
    PRIMARY KEY (community_id, index_id)
);

CREATE INDEX IF NOT EXISTS community_members_index_idx ON community_members(index_id);
CREATE INDEX IF NOT EXISTS community_members_level_idx ON community_members(level);

CREATE TABLE IF NOT EXISTS community_reports (
    community_id  TEXT PRIMARY KEY,
    level         INTEGER,
    title         TEXT,
    summary       TEXT,
    rating        REAL,                    -- 0-10 importance/impact rating
    findings      TEXT,                    -- JSON array of {summary, explanation}
    embedding     BLOB,                    -- float32 BLOB of the report summary
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS community_reports_level_idx ON community_reports(level);

-- FTS5 over documents.searchable. Manual sync via triggers below.
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    searchable, content='documents', content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, searchable) VALUES (new.rowid, new.searchable);
END;
CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, searchable) VALUES('delete', old.rowid, old.searchable);
END;
CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, searchable) VALUES('delete', old.rowid, old.searchable);
    INSERT INTO documents_fts(rowid, searchable) VALUES (new.rowid, new.searchable);
END;
