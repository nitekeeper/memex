"""Connection helpers with Memex-standard pragmas."""
from __future__ import annotations
import sqlite3
from pathlib import Path


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection with Memex pragmas applied.

    Pragmas:
      - journal_mode = WAL
      - synchronous  = NORMAL
      - foreign_keys = ON
      - temp_store   = MEMORY

    Returns a connection with row_factory set to sqlite3.Row (dict-like access).
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn


import os


def memex_home() -> Path:
    """Resolve the Memex home directory.

    Order: $MEMEX_HOME if set, else $HOME/.memex (POSIX) or
    $USERPROFILE/.memex (Windows).
    """
    explicit = os.environ.get("MEMEX_HOME")
    if explicit:
        return Path(explicit)
    user_home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if not user_home:
        raise RuntimeError("Cannot resolve user home directory")
    return Path(user_home) / ".memex"
