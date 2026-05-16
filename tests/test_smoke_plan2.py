import json
import pytest
from pathlib import Path
from unittest.mock import patch
from scripts import install, stores
from scripts.agents import librarian, reference_librarian, data_steward
from scripts.db import memex_home, get_connection


def test_e2e_index_write_and_search(tmp_memex_home, tmp_path):
    """Full write -> index -> search -> orphan-audit cycle."""
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

    # Mock Librarian LLM
    mock_lib_response = json.dumps({
        "index_id": "idx-1",
        "key": "hello-world",
        "domain": "article",
        "searchable": "hello world greeting body",
        "metadata": {},
        "relations": []
    })

    # Mock Reference Librarian LLM
    mock_rl_plan = json.dumps({
        "fts_query": "hello",
        "vector_query": None,
        "filters": {},
        "limit": 10,
    })

    with patch("scripts.agents.librarian._invoke_llm", return_value=mock_lib_response), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00\x00\x00\x00"), \
         patch("scripts.agents.reference_librarian._invoke_llm", return_value=mock_rl_plan):

        # Write
        result = librarian.index_write(
            payload={"title": "Hello", "body": "hello world greeting body"},
            target_store="test-articles",
            target_table="articles",
            caller_agent_id="librarian-1",
        )
        assert result["index_id"] == "idx-1"

        # Search
        results = reference_librarian.ask("hello")
        ids = [r["index_id"] for r in results]
        assert "idx-1" in ids

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
