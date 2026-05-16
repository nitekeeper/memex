-- article.db: default Brain store.
-- Created on plugin install. Schema is owned by Memex Brain.

CREATE TABLE IF NOT EXISTS articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    index_id     TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    source_url   TEXT,
    source_hash  TEXT,          -- canonicalized content hash for rerun safety
    body         TEXT NOT NULL,
    raw_path     TEXT,          -- pointer to ~/.memex/raw/...
    created_by   TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS articles_source_hash_idx ON articles(source_hash);

CREATE TABLE IF NOT EXISTS captures (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    index_id     TEXT NOT NULL UNIQUE,
    title        TEXT,
    body         TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS syntheses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    index_id     TEXT NOT NULL UNIQUE,
    topic        TEXT NOT NULL,
    body         TEXT NOT NULL,
    inputs_json  TEXT NOT NULL,   -- JSON array of source index_ids
    created_by   TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
