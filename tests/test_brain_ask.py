import json
import pytest
from unittest.mock import patch
from scripts import install, brain, onboarding
from scripts.db import memex_home, get_connection


@pytest.fixture
def installed_with_human(tmp_memex_home):
    install.run()
    onboarding.register_human("human-test", "Test", "User")


def test_ask_returns_results_from_index(installed_with_human):
    # Seed an index entry
    conn = get_connection(str(memex_home() / "index.db"))
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("idx-a", "k", "article", "article", "articles", "1", "cats are interesting", "librarian-1"),
    )
    conn.commit()
    conn.close()

    mock_plan = json.dumps({
        "fts_query": "cats",
        "vector_query": None,
        "filters": {},
        "limit": 5,
    })
    with patch("scripts.agents.reference_librarian._invoke_llm", return_value=mock_plan):
        results = brain.ask("tell me about cats")

    ids = [r["index_id"] for r in results]
    assert "idx-a" in ids


def test_ask_returns_empty_when_nothing_matches(installed_with_human):
    mock_plan = json.dumps({
        "fts_query": "nonexistent",
        "vector_query": None,
        "filters": {},
        "limit": 5,
    })
    with patch("scripts.agents.reference_librarian._invoke_llm", return_value=mock_plan):
        results = brain.ask("anything?")
    assert results == []
