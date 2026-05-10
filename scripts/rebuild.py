import os
import sqlite3
import frontmatter
import pathlib
from typing import Any


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


def parse_page(file_path: str) -> dict[str, Any]:
    """Read a .md file and return a structured dict for DB insertion.

    Returns a dict with normalized keys. If the file has no 'id' field,
    id is returned as '' so rebuild() can skip it with a warning.
    """
    post = frontmatter.load(file_path)
    meta = post.metadata
    stem = pathlib.Path(file_path).stem

    raw_id = str(meta.get("id", ""))
    project = raw_id.split(":")[0] if ":" in raw_id else ""

    return {
        "id": raw_id,
        "slug": str(meta.get("slug", stem)),
        "project": project,
        "title": str(meta.get("title", "")),
        "status": str(meta.get("status", "draft")),
        "synced_at_commit": meta.get("synced-at-commit"),
        "body": post.content,
        "file_path": file_path,
        "created": str(meta.get("created", "")),
        "updated": str(meta.get("updated", "")),
        "describes_files": list(meta.get("describes-files", [])),
        "tags": list(meta.get("tags", [])),
        "related": list(meta.get("related", [])),
    }
