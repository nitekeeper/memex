# db/

SQLite schema extension for Memex. Extends Skill Atelier's Stage 1 schema with project-wiki tables.

The framework's `db/schema.sql` defines the base schema (sources, lessons, wiki entries, sessions, products). Memex adds project-specific tables:

- `project_wiki_pages` — page metadata: id, slug, title, project, synced_at_commit, describes_files, status
- `project_wiki_fts` — FTS5 virtual table over page content

Schema will be written after the synthesis session and format/schema lock. See `ROADMAP.md`.
