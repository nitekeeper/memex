import pytest
from pathlib import Path
from scripts import install, stores
from scripts.agents import librarian, data_steward
from scripts.db import memex_home, get_connection


def test_e2e_index_write_and_audit(tmp_memex_home, tmp_path):
    """Full write (via new write_entry API) -> orphan-audit cycle.

    Phase 1 (Option-B refactor) coverage: Librarian's persistence layer
    via librarian.write_entry with synthetic LLM output. The search half
    of the original test (Reference Librarian) is deferred to Phase 2.
    """
    install.run()

    # Create a target store
    md = tmp_path / "m"; md.mkdir()
    (md / "001.sql").write_text(
        "CREATE TABLE articles ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "index_id TEXT NOT NULL UNIQUE, "
        "title TEXT NOT NULL, "
        "body TEXT NOT NULL"
        ");"
    )
    stores.create_store("test-articles", str(tmp_path / "ta.db"), str(md))

    # Synthetic Librarian subagent output (Task tool returns JSON; here we
    # supply it directly to write_entry).
    librarian_output = {
        "index_id": "idx-1",
        "key": "hello-world",
        "domain": "article",
        "searchable": "hello world greeting body",
        "metadata": {},
        "relations": [],
    }

    result = librarian.write_entry(
        payload={"title": "Hello", "body": "hello world greeting body"},
        librarian_output=librarian_output,
        target_store="test-articles",
        target_table="articles",
        caller_agent_id="librarian-1",
        embedding=b"\x00\x00\x00\x00",
    )
    assert result["index_id"] == "idx-1"

    # Audit should find no orphans (everything consistent)
    index_db = str(memex_home() / "index.db")
    orphans = data_steward.find_orphans(index_db)
    assert orphans == []


def test_e2e_orphan_creation_and_audit(tmp_memex_home, tmp_path):
    """Simulate the inconsistency window: index row exists, store row doesn't.
    Data Steward must detect."""
    install.run()

    md = tmp_path / "m"; md.mkdir()
    (md / "001.sql").write_text(
        "CREATE TABLE articles ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "index_id TEXT NOT NULL UNIQUE, "
        "body TEXT"
        ");"
    )
    stores.create_store("test-articles", str(tmp_path / "ta.db"), str(md))

    # Manually create an index row pointing to a nonexistent store row.
    index_db_path = str(memex_home() / "index.db")
    conn = get_connection(index_db_path)
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("idx-orphan", "x", "article", "test-articles", "articles", "99999", "txt", "librarian-1"),
    )
    conn.commit()
    conn.close()

    # Audit should detect
    report_path = data_steward.audit(index_db_path)
    content = Path(report_path).read_text()
    assert "idx-orphan" in content
    assert "Severity" in content


def test_e2e_install_is_complete(tmp_memex_home):
    """Confirms install.run produces a fully bootstrapped Memex install."""
    install.run()
    home = memex_home()
    assert (home / "agents.db").exists()
    assert (home / "index.db").exists()
    assert (home / "registry.json").exists()
    assert (home / "raw").is_dir()
    assert (home / "audits").is_dir()
