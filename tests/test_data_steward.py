import pytest
from pathlib import Path
from scripts import install, stores, registry
from scripts.agents import data_steward
from scripts.db import get_connection, memex_home


@pytest.fixture
def post_install(tmp_memex_home):
    install.run()
    return memex_home()


def _seed_doc(index_db: str, index_id: str, store: str, table: str, row_id: str):
    conn = get_connection(index_db)
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (index_id, "k", "article", store, table, row_id, "text", "librarian-1"),
    )
    conn.commit()
    conn.close()


def test_find_orphans_index_has_no_target_row(post_install, tmp_path):
    # Set up a registered store with one row.
    md = tmp_path / "m"; md.mkdir()
    (md / "001.sql").write_text(
        "CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, index_id TEXT, body TEXT);"
    )
    stores.create_store("test-store", str(tmp_path / "ts.db"), str(md))
    row = stores.insert("test-store", "items", {"index_id": "idx-A", "body": "x"})

    # Add an index entry that points to a row that doesn't exist.
    index_db = str(post_install / "index.db")
    _seed_doc(index_db, "idx-MISSING", "test-store", "items", "9999")

    orphans = data_steward.find_orphans(index_db)
    ids = {o["index_id"] for o in orphans}
    assert "idx-MISSING" in ids
    assert "idx-A" not in ids


def test_find_reverse_orphans_store_row_without_index_entry(post_install, tmp_path):
    md = tmp_path / "m"; md.mkdir()
    (md / "001.sql").write_text(
        "CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, index_id TEXT, body TEXT);"
    )
    stores.create_store("test-store", str(tmp_path / "ts.db"), str(md))
    # Insert a row WITHOUT registering in index.db
    stores.insert("test-store", "items", {"index_id": "idx-LONELY", "body": "x"})

    index_db = str(post_install / "index.db")
    reverse_orphans = data_steward.find_reverse_orphans(index_db, "test-store", "items")
    ids = {o["index_id"] for o in reverse_orphans}
    assert "idx-LONELY" in ids


def test_find_broken_relations(post_install):
    index_db = str(post_install / "index.db")
    _seed_doc(index_db, "a", "x", "t", "1")
    # b never inserted into documents
    # Insert a relation a → b directly (bypass FK by disabling temporarily)
    conn = get_connection(index_db)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute(
        "INSERT INTO relations (from_index_id, to_index_id, rel_type) VALUES (?, ?, ?)",
        ("a", "b", "cites"),
    )
    conn.commit()
    conn.close()

    broken = data_steward.find_broken_relations(index_db)
    assert len(broken) == 1
    assert broken[0]["to_index_id"] == "b"


def test_audit_writes_report_to_audits_dir(post_install, tmp_path):
    index_db = str(post_install / "index.db")
    _seed_doc(index_db, "idx-MISSING", "no-such-store", "t", "1")

    report_path = data_steward.audit(index_db)
    assert Path(report_path).exists()
    assert "idx-MISSING" in Path(report_path).read_text()


def test_audit_report_has_structured_sections(post_install):
    index_db = str(post_install / "index.db")
    report_path = data_steward.audit(index_db)
    content = Path(report_path).read_text()
    # Sections required by spec §11 audit format
    assert "## Summary" in content
    assert "## Findings" in content or "(no findings)" in content.lower()
    assert "Severity" in content or "(no findings)" in content.lower()
