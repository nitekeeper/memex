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
