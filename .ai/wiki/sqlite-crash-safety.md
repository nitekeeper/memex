---
id: memex:wiki:sqlite-crash-safety
slug: sqlite-crash-safety
title: SQLite crash safety requires WAL + synchronous=NORMAL
status: approved
tags: [sqlite, crash-safety, wal, configuration]
sources: [source:second-brain-blueprint]
related: []
proposed-in: session:2026-05-09
approved-in: session:2026-05-09
created: 2026-05-09
updated: 2026-05-09
---

# SQLite crash safety requires WAL + synchronous=NORMAL

The safe SQLite configuration for Memex is WAL journal mode with synchronous=NORMAL. The crash bug is MEMORY journal mode with synchronous=OFF — it skips the fsync, so a process kill between write and checkpoint silently loses data.

## The safe configuration

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
```

Set immediately after opening the connection, before any writes.

## Why the bug bites

`synchronous=OFF` tells SQLite not to wait for the OS to flush writes to disk. Combined with `journal_mode=MEMORY` (journal lives only in RAM), a crash or process kill between a write and its checkpoint produces a database that appears intact but has lost the in-flight transaction. The failure is silent — no error, no corruption flag, just missing data.

`journal_mode=WAL` with `synchronous=NORMAL` fsyncs at checkpoint time, not on every write. It is faster than the default DELETE mode and safe against process-kill: the WAL file is the durable record until checkpointed.

## What this rules out

- `PRAGMA synchronous = OFF` — never, for any write that must survive a crash.
- `PRAGMA journal_mode = MEMORY` — never in production; acceptable only for in-memory test databases with no durability requirement.

## How to apply

- All Memex DB connections open with the two PRAGMAs above.
- The `db/rebuild.py` script sets them before any schema migration or data load.
- Tests that use an in-memory SQLite (`:memory:`) are exempt — they have no durability requirement by definition.

## References

- `source:second-brain-blueprint` — SQLite crash-safety analysis; WAL + NORMAL identified as the fix.
- `db/schema.sql` — apply PRAGMAs here or in the connection initializer.
