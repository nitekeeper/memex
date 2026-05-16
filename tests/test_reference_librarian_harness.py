"""Reference Librarian harness tests — Phase 2 (Option-B Task-tool dispatch).

The Reference Librarian runs as a Claude Code subagent that builds a query
plan from the user's question. Python's role is prompt assembly, plan
parsing, and plan execution against index.db. There is no `_invoke_llm`
to mock — tests feed a synthetic query plan directly into `ask_execute`.
"""
import json
import pytest
from scripts.agents import reference_librarian as rl


def test_build_prompt_includes_profile(tmp_memex_home):
    from scripts import install
    install.run()
    prompt = rl.build_prompt(query="what is X?", caller_agent_id="reference-librarian-1")
    assert "Whitfield" in prompt
    assert "what is X?" in prompt


def test_fetch_context_returns_profile_and_name(tmp_memex_home):
    from scripts import install
    install.run()
    ctx = rl.fetch_context()
    assert ctx["name"] == "Dr. Eleanor Whitfield"
    assert "Whitfield" in ctx["profile"] or "Reference" in ctx["profile"]


def test_ask_prepare_returns_subagent_prompt(tmp_memex_home):
    from scripts import install
    install.run()
    prep = rl.ask_prepare("tell me about cats")
    assert prep["status"] == "ready"
    assert prep["query"] == "tell me about cats"
    assert "tell me about cats" in prep["subagent_prompt"]
    assert "Whitfield" in prep["subagent_prompt"]


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


def test_parse_query_plan_strips_code_fences():
    fenced = "```json\n" + json.dumps({"fts_query": "x"}) + "\n```"
    parsed = rl.parse_query_plan(fenced)
    assert parsed["fts_query"] == "x"


def test_execute_query_plan_fts_only(tmp_memex_home, tmp_path):
    """FTS5-only execution (no embedding pathway)."""
    from scripts import install
    install.run()
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


def test_ask_execute_with_synthetic_plan(tmp_memex_home):
    """End-to-end ask flow with synthetic Reference Librarian output."""
    from scripts import install
    install.run()
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

    prep = rl.ask_prepare("tell me about cats")
    synthetic_plan = {
        "fts_query": "cats",
        "vector_query": None,
        "filters": {},
        "limit": 5,
    }
    results = rl.ask_execute(prep, synthetic_plan, with_embedding=False)
    ids = [r["index_id"] for r in results]
    assert "a" in ids


def test_ask_execute_refuses_non_ready_prepare():
    bad_prep = {"status": "error"}
    with pytest.raises(ValueError):
        rl.ask_execute(bad_prep, {"fts_query": "x"})


def test_ask_execute_filters_by_domain(tmp_memex_home):
    """Plan filters carry through to the SQL WHERE clause."""
    from scripts import install
    install.run()
    from scripts.db import get_connection, memex_home
    conn = get_connection(str(memex_home() / "index.db"))
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("art-1", "a", "article", "no-store", "t", "1", "cats and dogs", "librarian-1"),
    )
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("dec-1", "d", "decision", "no-store", "t", "2", "cats and dogs", "librarian-1"),
    )
    conn.commit()
    conn.close()

    plan = {
        "fts_query": "cats",
        "vector_query": None,
        "filters": {"domain": "article"},
        "limit": 10,
    }
    results = rl.execute_query_plan(plan, with_embedding=False)
    ids = [r["index_id"] for r in results]
    assert "art-1" in ids
    assert "dec-1" not in ids
