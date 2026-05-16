import json
import pytest
from unittest.mock import patch, MagicMock
from scripts.agents import reference_librarian as rl


def test_build_prompt_includes_profile(tmp_memex_home):
    from scripts import install
    install.run()
    prompt = rl.build_prompt(query="what is X?", caller_agent_id="reference-librarian-1")
    assert "Whitfield" in prompt
    assert "what is X?" in prompt


def test_parse_query_plan():
    mock_plan = json.dumps({
        "fts_query": "machine learning",
        "vector_query": "machine learning",
        "filters": {"domain": "article"},
        "limit": 10,
    })
    parsed = rl.parse_query_plan(mock_plan)
    assert parsed["fts_query"] == "machine learning"
    assert parsed["filters"]["domain"] == "article"


def test_execute_query_plan_fts_only(tmp_memex_home, tmp_path):
    """Test execution with FTS5 only (no embedding)."""
    from scripts import install
    install.run()
    # Seed an index entry
    from scripts.db import get_connection, memex_home
    conn = get_connection(str(memex_home() / "index.db"))
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("a", "x", "article", "no-store", "t", "1", "machine learning is great", "librarian-1"),
    )
    conn.commit()
    conn.close()

    plan = {
        "fts_query": "machine learning",
        "vector_query": None,
        "filters": {},
        "limit": 5,
    }
    results = rl.execute_query_plan(plan, with_embedding=False)
    ids = [r["index_id"] for r in results]
    assert "a" in ids


def test_ask_returns_ranked_results(tmp_memex_home):
    from scripts import install
    install.run()
    # Seed two entries with overlapping content
    from scripts.db import get_connection, memex_home
    conn = get_connection(str(memex_home() / "index.db"))
    for index_id, text in [("a", "cats are interesting"), ("b", "dogs are fun")]:
        conn.execute(
            "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (index_id, index_id, "article", "no-store", "t", index_id, text, "librarian-1"),
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
        results = rl.ask("tell me about cats")

    ids = [r["index_id"] for r in results]
    assert "a" in ids
