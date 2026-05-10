import os
import sqlite3
import pytest

from rebuild import connect

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")


def test_connect_creates_tables(tmp_path):
    db_path = str(tmp_path / "memex.db")
    conn = connect(db_path, SCHEMA_PATH)

    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    assert "pages" in tables
    assert "links" in tables
    assert "page_files" in tables
    assert "page_tags" in tables
    conn.close()


def test_connect_sets_wal_mode(tmp_path):
    db_path = str(tmp_path / "memex.db")
    conn = connect(db_path, SCHEMA_PATH)

    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"
    conn.close()


def test_connect_wipes_existing_db(tmp_path):
    db_path = str(tmp_path / "memex.db")
    # First build
    conn = connect(db_path, SCHEMA_PATH)
    conn.execute("INSERT INTO pages (id, slug, project, title, status, body, file_path, created, updated) "
                 "VALUES ('x', 'x', 'x', 'x', 'draft', '', 'x.md', '2026-01-01', '2026-01-01')")
    conn.commit()
    conn.close()
    # Rebuild — should wipe and start fresh
    conn = connect(db_path, SCHEMA_PATH)
    count = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    assert count == 0
    conn.close()
