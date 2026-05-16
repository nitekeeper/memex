-- Universal migrations tracker. Memex DBA injects this into every store
-- BEFORE running consumer-supplied migrations. IF NOT EXISTS makes consumer
-- migrations that declare their own `migrations` table a safe no-op
-- (provided they also use IF NOT EXISTS).
CREATE TABLE IF NOT EXISTS migrations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT NOT NULL UNIQUE,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
