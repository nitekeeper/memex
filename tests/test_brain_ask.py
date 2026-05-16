"""brain.ask_prepare / ask_execute tests — Phase 2 (Option-B Task-tool dispatch).

The Reference Librarian subagent's role is faked by passing synthetic
query plans directly to ask_execute.
"""
import pytest
from scripts import install, brain, onboarding
from scripts.db import memex_home, get_connection


@pytest.fixture
def installed_with_human(tmp_memex_home):
    install.run()
    onboarding.register_human("human-test", "Test", "User")


def test_ask_prepare_returns_subagent_prompt(installed_with_human):
    prep = brain.ask_prepare("tell me about cats")
    assert prep["status"] == "ready"
    assert prep["query"] == "tell me about cats"
    assert "tell me about cats" in prep["subagent_prompt"]


def test_ask_execute_returns_results_from_index(installed_with_human):
    conn = get_connection(str(memex_home() / "index.db"))
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("idx-a", "k", "article", "article", "articles", "1", "cats are interesting", "librarian-1"),
    )
    conn.commit()
    conn.close()

    prep = brain.ask_prepare("tell me about cats")
    synthetic_plan = {
        "fts_query": "cats",
        "vector_query": None,
        "filters": {},
        "limit": 5,
    }
    results = brain.ask_execute(prep, synthetic_plan)
    ids = [r["index_id"] for r in results]
    assert "idx-a" in ids


def test_ask_execute_returns_empty_when_nothing_matches(installed_with_human):
    prep = brain.ask_prepare("anything?")
    synthetic_plan = {
        "fts_query": "nonexistent",
        "vector_query": None,
        "filters": {},
        "limit": 5,
    }
    results = brain.ask_execute(prep, synthetic_plan)
    assert results == []
