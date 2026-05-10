---
id: source:sqlite-crash-safety
slug: sqlite-crash-safety
title: SQLite Crash Safety — WAL Mode, Journaling, and Corruption Causes
type: article
authors: [D. Richard Hipp, SQLite contributors]
url: "https://www.sqlite.org/wal.html | https://www.sqlite.org/howtocorrupt.html | https://www.sqlite.org/atomiccommit.html"
captured: 2026-05-09
status: analyzed
relevance-to: [memex, second-brain-blueprint]
tags: [sqlite, crash-safety, wal, journal, corruption, fts5]
informs-decisions: []
---

# SQLite Crash Safety — WAL Mode, Journaling, and Corruption

## Summary

SQLite provides two fundamentally different mechanisms for atomic commits: the traditional rollback journal (default `DELETE` mode) and Write-Ahead Logging (WAL). When a crash occurs, SQLite leaves behind a "hot journal" file (`-journal` or `-wal`) that it uses to automatically recover on next open — this is by design, not a sign of corruption. Actual corruption happens when that journal is deleted, moved, or paired with the wrong database file before recovery completes, or when sync is disabled, or when connections are shared across forks/threads incorrectly. WAL mode is materially more crash-resilient than rollback mode and is the recommended mode for any application that experiences crashes.

## Key claims

- **A journal file after crash is normal, not corruption**: SQLite's hot journal is the recovery mechanism. Corruption occurs when the journal is interfered with (deleted, moved, mismatched) *before* SQLite can replay it. The next `sqlite3.connect()` call should auto-recover if the journal is intact and untouched.
- **WAL mode is more forgiving of out-of-order writes**: In rollback mode, a write reorder during power failure can corrupt the database. In WAL mode, the original database file is never modified during a transaction — only the WAL file is written — so a crash during commit primarily affects durability, not consistency.
- **Never delete a `-journal` or `-wal` file manually**: These files contain live recovery data. Deleting a hot journal leaves the database in a partially-written state with no way to roll back.
- **`synchronous=OFF` is the highest-risk pragma**: It disables all fsync() calls; OS write reordering after a power failure guarantees corruption. Default (`FULL`) should never be lowered in production.
- **`close()` in one thread drops all POSIX advisory locks for all threads**: If any thread in a Python process calls `close()` on the database file descriptor while other connections are open, SQLite's locks evaporate. This is a silent corruption vector in multi-threaded apps.
- **Never use an SQLite connection across `fork()`**: Connections opened in the parent must not be used in the child. Call `sqlite3_close()` only from the process that opened the connection.
- **WAL mode persists across reconnects**: Setting `PRAGMA journal_mode=WAL` is sticky — it survives database close/reopen. No need to set it on every connection.
- **WAL requires all processes on the same host**: Network filesystem (NFS) + WAL = unsupported; requires shared memory (`-shm` file) accessible to all readers.
- **WAL-reset race condition in SQLite ≤ 3.51.2**: A data race in concurrent write+checkpoint on WAL databases can corrupt the WAL index. Probability is extremely low but upgrade to 3.51.3+ is recommended.
- **PERSIST journal mode is faster than DELETE with equivalent crash safety**: Zero-ing the journal header is cheaper than deleting the file. Useful where DELETE mode is causing write amplification.
- **Python's `sqlite3` module uses `check_same_thread=True` by default**: Sharing a connection across threads without this flag is undefined behavior; use per-thread connections or an explicit lock.

## Relevance

**For the second-brain-blueprint wiki's crash-corruption problem:**

The most likely root cause when a user sees a `-journal` file after a crash and gets corruption is one of:
1. The journal was deleted or moved (e.g., by a cleanup script, backup tool, or the user manually) before SQLite could replay it.
2. The Python `sqlite3` connection was not properly closed (missing `conn.close()` or context manager), leaving a write transaction partially committed when the process died.
3. `synchronous=OFF` or `synchronous=NORMAL` was set somewhere in the skill's schema init or query layer.
4. A backup script copied the `.db` file without also copying the `.db-journal` file, producing a mismatched pair.

**Mitigation hierarchy (highest to lowest impact):**
1. Switch to WAL mode (`PRAGMA journal_mode=WAL`).
2. Verify `synchronous` is `FULL` or `NORMAL` (never `OFF`).
3. Use Python context managers (`with sqlite3.connect(...) as conn:`) to guarantee connection close on exit.
4. Never run file-level backups on a live SQLite DB; use `VACUUM INTO` or the backup API instead.
5. Never delete `.db-journal` or `.db-wal` files manually.

**For Memex's `search` skill (SQLite FTS5):**

Memex will embed SQLite. These principles should be baked into the skill spec from day one — especially WAL mode as the default, connection lifecycle hygiene, and the prohibition on deleting journal files.

## Open questions

- The blueprint's `sqlite-query` skill initializes FTS5 via Python scripts. Does it set `journal_mode=WAL` at init time? If not, this is the most likely single fix for the user's corruption issue.
- Does the blueprint's backup flow (if any) use `VACUUM INTO` or raw file copy? Raw copy without the journal is a silent corruption source.
- Python's `sqlite3.connect()` returns a connection in autocommit-off mode by default. Are all write paths in the skill properly committing/rolling back, or are some leaving implicit transactions open on crash?
- WAL mode requires write access to the directory for the `-shm` file. If the wiki is stored in a read-only or restricted path, WAL activation may silently fall back to DELETE mode. The `PRAGMA journal_mode` return value should be checked.

## Excerpts

> "SQLite in WAL mode is more forgiving of out-of-order writes. Corruption during a COMMIT in WAL mode is less likely; failures primarily affect durability during checkpoint operations." — howtocorrupt.html §3.1

> "SQLite always writes a complete sector of data, even if the page size of the database is smaller than the sector size." — atomiccommit.html (on why rollback journals can leave partial sectors)

> "A journal is considered 'hot' if: the rollback journal file exists, the journal file is not empty, there is no reserved lock on the main database file, the journal header is well-formed." — atomiccommit.html §4.2 (the exact conditions SQLite checks on open)

> "If an incorrect checksum is seen, the rollback is abandoned... the checksum does at least make such an error unlikely." — atomiccommit.html (on synchronous=NORMAL partial protection)

> "Never call sqlite3_close() on a connection from a child process if opened in the parent." — howtocorrupt.html §2.7
