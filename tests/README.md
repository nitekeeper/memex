# tests/

Validation for Memex skills. Populated during the build phase.

Key scenarios to cover:
- `capture`: given a session, writes a correctly-formed wiki page
- `sync`: correctly identifies stale pages (describes-files changed after synced-at-commit)
- `sync`: correctly identifies current pages (no describes-files changed)
- `search`: FTS5 returns relevant results for a query
