"""Database connection and Memex home-directory helpers."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

MEMEX_DIR_NAME = ".memex"


def get_connection(db_path: str | os.PathLike[str]) -> sqlite3.Connection:
    """Open a SQLite connection with Memex pragmas applied.

    Pragmas:
      - journal_mode = WAL
      - synchronous  = NORMAL
      - foreign_keys = ON
      - temp_store   = MEMORY

    Returns a connection with row_factory set to sqlite3.Row (dict-like access).

    Raises:
      RuntimeError: if WAL journal mode could not be enabled (e.g. on a
        filesystem that does not support it).
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
    if mode.lower() != "wal":
        conn.close()
        raise RuntimeError(f"Could not enable WAL mode (got {mode!r})")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn


def memex_home() -> Path:
    """Resolve the Memex home directory.

    Order: $MEMEX_HOME if set, else Path.home() / .memex (which respects
    $HOME on POSIX and $USERPROFILE on Windows).

    The returned path is not guaranteed to exist; callers should mkdir as needed.
    """
    explicit = os.environ.get("MEMEX_HOME")
    if explicit:
        return Path(explicit)
    return Path.home() / MEMEX_DIR_NAME
