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
