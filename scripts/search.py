import argparse
import json
import os
import sqlite3
import sys
from typing import Optional


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def search(
    db_path: str,
    query: str,
    limit: int = 10,
    status: Optional[str] = None,
    tags: Optional[list] = None,
) -> dict:
    if not query.strip():
        raise ValueError("query cannot be empty")
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"DB not found: {db_path}")

    conn = _connect(db_path)
    try:
        sql = """
            SELECT p.id, p.title, p.file_path, p.status, p.updated,
                   snippet(pages_fts, 2, '[', ']', '...', 20) AS snippet,
                   bm25(pages_fts) AS score
            FROM pages_fts
            JOIN pages p ON pages_fts.rowid = p.rowid
            WHERE pages_fts MATCH ?
        """
        params: list = [query]

        if status:
            sql += " AND p.status = ?"
            params.append(status)

        if tags:
            for tag in tags:
                sql += " AND p.id IN (SELECT page_id FROM page_tags WHERE tag = ?)"
                params.append(tag)

        sql += " ORDER BY bm25(pages_fts) LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return {
            "query": query,
            "results": [dict(row) for row in rows],
        }
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search memex.db via FTS5.")
    parser.add_argument("ai_dir", help="Path to the project's .ai/ directory")
    parser.add_argument("query", help="FTS5 search string")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--status", default=None)
    parser.add_argument("--tag", action="append", dest="tags", default=None)
    args = parser.parse_args()

    db_path = os.path.join(args.ai_dir, "memex.db")

    try:
        result = search(
            db_path, args.query,
            limit=args.limit,
            status=args.status,
            tags=args.tags or [],
        )
        print(json.dumps(result, indent=2))
    except (ValueError, FileNotFoundError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
