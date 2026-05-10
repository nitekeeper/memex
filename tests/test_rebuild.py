import os
import sqlite3
import pathlib
import pytest
import tempfile
import textwrap

from rebuild import connect, parse_page

SCHEMA_PATH = str(pathlib.Path(__file__).parent.parent / "db" / "schema.sql")


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


def test_connect_enforces_foreign_keys(tmp_path):
    db_path = str(tmp_path / "memex.db")
    conn = connect(db_path, SCHEMA_PATH)
    fk_on = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk_on == 1
    conn.close()


FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "sample" / ".ai" / "wiki"


def test_parse_concept_page():
    page = parse_page(str(FIXTURES / "concept-page.md"))
    assert page["id"] == "sample:wiki:auth-design"
    assert page["title"] == "Auth design decisions"
    assert page["status"] == "draft"
    assert page["created"] == "2026-05-09"
    assert page["updated"] == "2026-05-09"
    assert page["slug"] == "concept-page"          # derived from filename stem
    assert page["project"] == "sample"              # extracted from id prefix
    assert page["synced_at_commit"] is None
    assert page["describes_files"] == []
    assert page["tags"] == ["auth", "design"]
    assert page["body"].strip() == "This is the body of the auth design page."
    assert page["file_path"].endswith("concept-page.md")


def test_parse_code_page():
    page = parse_page(str(FIXTURES / "code-page.md"))
    assert page["id"] == "sample:wiki:db-schema"
    assert page["slug"] == "db-schema"              # from frontmatter, not filename
    assert page["synced_at_commit"] == "f88c1c6"
    assert page["describes_files"] == ["db/schema.sql", "db/migrations/"]
    assert page["tags"] == ["database", "schema"]
    assert page["related"] == ["sample:wiki:auth-design"]


def test_parse_missing_id_returns_empty_id():
    content = textwrap.dedent("""\
        ---
        title: No ID page
        status: draft
        created: 2026-05-09
        updated: 2026-05-09
        ---
        Body text.
    """)
    with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
        f.write(content)
        tmp = f.name
    page = parse_page(tmp)
    assert page["id"] == ""
    os.unlink(tmp)
