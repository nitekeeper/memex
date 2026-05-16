import os
import sqlite3
import pathlib
import pytest
import tempfile
import textwrap

from scripts.rebuild import connect, parse_page, load_page, _insert_links, rebuild

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
    import datetime
    page = parse_page(str(FIXTURES / "concept-page.md"))
    assert page["id"] == "sample:wiki:auth-design"
    assert page["title"] == "Auth design decisions"
    assert page["status"] == "draft"
    assert page["created"] == datetime.date(2026, 5, 9)
    assert page["updated"] == datetime.date(2026, 5, 9)
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


def test_parse_malformed_id_returns_empty_project(tmp_path):
    p = tmp_path / "malformed.md"
    p.write_text(textwrap.dedent("""\
        ---
        id: sample:auth-design
        title: Malformed ID
        status: draft
        created: 2026-05-09
        updated: 2026-05-09
        ---
        Body.
    """))
    page = parse_page(str(p))
    assert page["project"] == ""   # two-segment id is not a valid <project>:<type>:<slug>
    assert page["id"] == "sample:auth-design"


def test_parse_missing_id_returns_empty_id(tmp_path):
    p = tmp_path / "no-id.md"
    p.write_text(textwrap.dedent("""\
        ---
        title: No ID page
        status: draft
        created: 2026-05-09
        updated: 2026-05-09
        ---
        Body text.
    """))
    page = parse_page(str(p))
    assert page["id"] == ""


def test_load_concept_page(tmp_path):
    db_path = str(tmp_path / "memex.db")
    conn = connect(db_path, SCHEMA_PATH)
    page = parse_page(str(FIXTURES / "concept-page.md"))
    load_page(conn, page)
    conn.commit()

    row = conn.execute("SELECT * FROM pages WHERE id = ?", (page["id"],)).fetchone()
    assert row is not None
    assert row["title"] == "Auth design decisions"
    assert row["status"] == "draft"
    assert row["synced_at_commit"] is None

    tags = sorted(r["tag"] for r in conn.execute(
        "SELECT tag FROM page_tags WHERE page_id = ?", (page["id"],)
    ))
    assert tags == ["auth", "design"]

    files = conn.execute(
        "SELECT * FROM page_files WHERE page_id = ?", (page["id"],)
    ).fetchall()
    assert files == []
    conn.close()


def test_load_code_page(tmp_path):
    db_path = str(tmp_path / "memex.db")
    conn = connect(db_path, SCHEMA_PATH)

    # Load concept page first — its id is the link target in code-page's 'related' field
    concept = parse_page(str(FIXTURES / "concept-page.md"))
    load_page(conn, concept)

    page = parse_page(str(FIXTURES / "code-page.md"))
    load_page(conn, page)
    _insert_links(conn, page)
    conn.commit()

    row = conn.execute("SELECT * FROM pages WHERE id = ?", (page["id"],)).fetchone()
    assert row["synced_at_commit"] == "f88c1c6"

    files = sorted(
        r["file_path"] for r in conn.execute(
            "SELECT file_path FROM page_files WHERE page_id = ?", (page["id"],)
        )
    )
    assert files == ["db/migrations/", "db/schema.sql"]

    links = conn.execute(
        "SELECT to_id, rel_type FROM links WHERE from_id = ?", (page["id"],)
    ).fetchall()
    assert len(links) == 1
    assert links[0]["to_id"] == "sample:wiki:auth-design"
    assert links[0]["rel_type"] == "related"
    conn.close()


AI_DIR = str(FIXTURES.parent)  # tests/fixtures/sample/.ai/


def test_rebuild_populates_all_pages(tmp_path):
    db_path = str(tmp_path / "memex.db")
    rebuild(AI_DIR, db_path, SCHEMA_PATH)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    count = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    assert count == 2
    conn.close()


def test_rebuild_fts_search(tmp_path):
    db_path = str(tmp_path / "memex.db")
    rebuild(AI_DIR, db_path, SCHEMA_PATH)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    results = conn.execute(
        "SELECT id FROM pages_fts WHERE pages_fts MATCH ?", ("database",)
    ).fetchall()
    assert len(results) == 1
    assert results[0]["id"] == "sample:wiki:db-schema"
    conn.close()


def test_rebuild_skips_pages_without_id(tmp_path):
    import textwrap, shutil
    fixture_copy = tmp_path / "sample" / ".ai"
    shutil.copytree(FIXTURES.parent, fixture_copy)
    bad_page = fixture_copy / "wiki" / "no-id.md"
    bad_page.write_text(textwrap.dedent("""\
        ---
        title: No ID
        status: draft
        created: 2026-05-09
        updated: 2026-05-09
        ---
        Body.
    """))
    db_path = str(tmp_path / "memex.db")
    rebuild(str(fixture_copy), db_path, SCHEMA_PATH)

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    assert count == 2  # bad page skipped, original 2 loaded
    conn.close()
