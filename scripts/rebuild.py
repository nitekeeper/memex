import os
import sqlite3


def connect(db_path: str, schema_path: str) -> sqlite3.Connection:
    """Open (or recreate) memex.db with WAL safety and schema applied.

    The caller must close any existing connection to db_path before calling
    this function. On Windows, os.remove() will raise PermissionError if the
    file is held open by another connection.
    """
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
    assert mode == "wal", f"WAL mode not set; got {mode!r}"
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    with open(schema_path) as f:
        schema_sql = f.read()
    # executescript() issues an implicit COMMIT before running — callers must not
    # hold an open transaction before calling connect().
    conn.executescript(schema_sql)
    return conn
