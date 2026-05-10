import os
import sqlite3


def connect(db_path: str, schema_path: str) -> sqlite3.Connection:
    """Open (or recreate) memex.db with WAL safety and schema applied."""
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    with open(schema_path) as f:
        schema_sql = f.read()
    conn.executescript(schema_sql)
    return conn
