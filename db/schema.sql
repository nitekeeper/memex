-- Memex SQLite schema — v0.1
-- Locked at synthesis session 2026-05-09.
-- One DB per project, co-located at .ai/memex.db.
-- The DB is a derived artifact: rebuilt from markdown source files via rebuild script.
-- Do not edit rows directly; edit the markdown and rebuild.

-- Safety: WAL + NORMAL (see wiki:sqlite-crash-safety)
-- These PRAGMAs must be set on every connection open, not just at schema creation.
-- The rebuild script's connect() helper is responsible for setting them before any query.
-- PRAGMA journal_mode = WAL;
-- PRAGMA synchronous = NORMAL;

-- Core page table.
-- Each row corresponds to one .md file in .ai/wiki/ (or .ai/ACTIVE.md, etc.).
CREATE TABLE pages (
    id               TEXT PRIMARY KEY,   -- full namespaced id: <project>:<type>:<slug>
    slug             TEXT NOT NULL,       -- inner slug only, no prefix
    project          TEXT NOT NULL,       -- project identifier, for scoping queries
    title            TEXT NOT NULL,
    status           TEXT NOT NULL CHECK(status IN ('draft', 'approved', 'archived')),
    synced_at_commit TEXT,               -- null = concept/decision page, no file-bound staleness
    body             TEXT NOT NULL DEFAULT '',
    file_path        TEXT NOT NULL,       -- path to source .md file, used by rebuild script
    created          TEXT NOT NULL,       -- YYYY-MM-DD
    updated          TEXT NOT NULL        -- YYYY-MM-DD
);

-- Cross-page and cross-entity relationships.
-- from_id is always a local page id.
-- to_id is TEXT (not FK): may reference pages in other projects, framework entities, or
-- external IDs not present in this DB.
-- rel_type examples: 'related', 'supersedes', 'describes', 'proposed-in', 'approved-in'
CREATE TABLE links (
    from_id          TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    to_id            TEXT NOT NULL,
    rel_type         TEXT NOT NULL,
    PRIMARY KEY (from_id, to_id, rel_type)
);

-- Source files a page tracks for staleness detection.
-- Staleness query: given a changed file path and current HEAD SHA,
-- find pages where file_path matches AND synced_at_commit != HEAD.
CREATE TABLE page_files (
    page_id          TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    file_path        TEXT NOT NULL,
    PRIMARY KEY (page_id, file_path)
);

-- Tag index for filtered queries ("all approved pages tagged 'schema'").
CREATE TABLE page_tags (
    page_id          TEXT NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    tag              TEXT NOT NULL,
    PRIMARY KEY (page_id, tag)
);

-- Indexes
CREATE INDEX idx_pages_project        ON pages(project);
CREATE INDEX idx_pages_status         ON pages(status, project);
CREATE INDEX idx_pages_updated        ON pages(updated);
CREATE INDEX idx_links_to_id          ON links(to_id);
CREATE INDEX idx_page_files_file_path ON page_files(file_path);
CREATE INDEX idx_page_tags_tag        ON page_tags(tag);

-- Full-text search over page titles and bodies.
-- Content mode: FTS table references pages(rowid) rather than duplicating text.
-- Since the DB is rebuilt from scratch (not incrementally updated), no sync triggers needed.
-- Stage 2 upgrade path: add embedding column to pages + sqlite-vec virtual table alongside this.
CREATE VIRTUAL TABLE pages_fts USING fts5(
    id    UNINDEXED,
    title,
    body,
    content='pages',
    content_rowid='rowid'
);
