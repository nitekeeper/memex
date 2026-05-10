import os
import sqlite3
import glob as glob_module
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
    parts = raw_id.split(":", 2)
    project = parts[0] if len(parts) == 3 else ""

    return {
        "id": raw_id,
        "slug": str(meta.get("slug", stem)),
        "project": project,
        "title": str(meta.get("title", "")),
        "status": str(meta.get("status", "draft")),
        "synced_at_commit": meta.get("synced-at-commit"),
        "body": post.content,
        "file_path": file_path,
        "created": meta.get("created"),
        "updated": meta.get("updated"),
        "describes_files": list(meta.get("describes-files", [])),
        "tags": list(meta.get("tags", [])),
        "related": list(meta.get("related", [])),
    }


def load_page(conn: sqlite3.Connection, page: dict[str, Any]) -> None:
    """Insert a parsed page dict into all four normalized tables.

    Does not commit — caller is responsible for committing after all pages
    are loaded (for atomicity across the full rebuild).

    created/updated: parse_page() may return datetime.date objects or None.
    SQLite requires TEXT for these NOT NULL columns, so we coerce to ISO
    string here, defaulting to "" when absent.
    """
    def _date_str(val: Any) -> str:
        if val is None:
            return ""
        return str(val)  # datetime.date.__str__ returns YYYY-MM-DD

    conn.execute(
        """INSERT INTO pages
           (id, slug, project, title, status, synced_at_commit,
            body, file_path, created, updated)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            page["id"], page["slug"], page["project"], page["title"],
            page["status"], page["synced_at_commit"], page["body"],
            page["file_path"], _date_str(page["created"]), _date_str(page["updated"]),
        ),
    )
    for tag in page["tags"]:
        conn.execute(
            "INSERT INTO page_tags (page_id, tag) VALUES (?, ?)",
            (page["id"], tag),
        )
    for file_path in page["describes_files"]:
        conn.execute(
            "INSERT INTO page_files (page_id, file_path) VALUES (?, ?)",
            (page["id"], file_path),
        )


def _insert_links(conn: sqlite3.Connection, page: dict[str, Any]) -> None:
    """Insert link rows for a page. Called in pass 2, after all pages exist."""
    for to_id in page["related"]:
        conn.execute(
            "INSERT OR IGNORE INTO links (from_id, to_id, rel_type) VALUES (?, ?, ?)",
            (page["id"], to_id, "related"),
        )


def rebuild(ai_dir: str, db_path: str, schema_path: str) -> None:
    """Walk .ai/ directory, parse all .md files, and populate memex.db.

    Two-pass strategy to avoid FK violations on links:
    Pass 1 — insert all pages (pages, page_tags, page_files)
    Pass 2 — insert all links (after all pages exist)
    """
    conn = connect(db_path, schema_path)
    try:
        pattern = os.path.join(ai_dir, "**", "*.md")
        md_files = glob_module.glob(pattern, recursive=True)

        pages = []
        for file_path in sorted(md_files):
            page = parse_page(file_path)
            if not page["id"]:
                print(f"WARNING: skipping {file_path} — missing id field")
                continue
            pages.append(page)

        # Pass 1: insert pages, tags, files
        for page in pages:
            load_page(conn, page)

        # Pass 2: insert links (all pages now exist, FK safe)
        for page in pages:
            _insert_links(conn, page)

        # Rebuild FTS index from pages table content
        conn.execute("INSERT INTO pages_fts(pages_fts) VALUES('rebuild')")
        conn.commit()
    finally:
        conn.close()
