"""Database connection and Memex home-directory helpers."""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

MEMEX_DIR_NAME = ".memex"

# SQLite identifier syntax: ASCII letter or underscore, followed by letters,
# digits, or underscores. Anything else is rejected to prevent SQL injection
# through interpolated identifiers (SQLite parameter binding only handles
# values, not table or column names — so identifiers must be interpolated,
# but only after this whitelist check).
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def safe_identifier(name: str) -> str:
    """Validate a SQL identifier (table or column name) before interpolation.

    SQLite has no parameter binding for identifiers, so they must be
    interpolated into the query string. This helper enforces a whitelist
    of safe characters: ASCII letter/underscore start, then alphanumerics
    or underscores. Anything else raises ValueError.

    Use this at every site that interpolates an identifier into a query
    where the identifier comes from outside the module (caller payloads,
    consumer migrations, etc.). It is the only sanctioned mechanism for
    identifier interpolation in this codebase.
    """
    if not isinstance(name, str):
        raise ValueError(f"identifier must be str, got {type(name).__name__}")
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"invalid SQL identifier: {name!r}. Allowed: [A-Za-z_][A-Za-z0-9_]*")
    return name


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
