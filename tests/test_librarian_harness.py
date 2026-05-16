import json
import pytest
from unittest.mock import patch, MagicMock
from scripts.agents import librarian


def test_build_prompt_includes_agent_profile(tmp_memex_home):
    from scripts import install
    install.run()
    prompt = librarian.build_prompt(
        payload="hello world",
        target_store="article",
        caller_agent_id="librarian-1",
    )
    # Profile content should be embedded
    assert "Ranganathan" in prompt
    assert "hello world" in prompt
    assert "target_store" in prompt or "article" in prompt


def test_build_prompt_includes_existing_index_snippet(tmp_memex_home):
    """Prompt must include a snippet of existing index for context."""
    from scripts import install
    install.run()
    prompt = librarian.build_prompt(
        payload="hello",
        target_store="article",
        caller_agent_id="librarian-1",
        existing_index_snippet=[
            {"index_id": "x", "key": "prior-article", "domain": "article"}
        ],
    )
    assert "prior-article" in prompt


def test_parse_response_extracts_structured_output():
    mock_response = json.dumps({
        "index_id": "idx-abc",
        "key": "test-key",
        "domain": "article",
        "searchable": "test searchable text",
        "metadata": {"author": "X"},
        "relations": [
            {"to_index_id": "idx-other", "rel_type": "cites"}
        ]
    })
    parsed = librarian.parse_response(mock_response)
    assert parsed["index_id"] == "idx-abc"
    assert parsed["domain"] == "article"
    assert parsed["relations"][0]["rel_type"] == "cites"


def test_parse_response_raises_on_missing_required_field():
    bad_response = json.dumps({"index_id": "x"})  # missing domain, key, searchable
    with pytest.raises(ValueError):
        librarian.parse_response(bad_response)


def test_index_write_invokes_librarian_and_persists(tmp_memex_home, tmp_path):
    """End-to-end harness test with mocked LLM call."""
    from scripts import install, stores
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

    mock_llm = MagicMock(return_value=json.dumps({
        "index_id": "idx-test-1",
        "key": "hello-world",
        "domain": "article",
        "searchable": "hello world body content",
        "metadata": {"topic": "greeting"},
        "relations": []
    }))

    with patch("scripts.agents.librarian._invoke_llm", mock_llm), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00" * 4):
        result = librarian.index_write(
            payload={"title": "Hello", "body": "hello world body content"},
            target_store="test-articles",
            target_table="articles",
            caller_agent_id="librarian-1",
        )

    assert result["index_id"] == "idx-test-1"

    # Verify index.db row was written
    from scripts.db import memex_home
    from scripts.db import get_connection
    conn = get_connection(str(memex_home() / "index.db"))
    row = conn.execute("SELECT * FROM documents WHERE index_id = ?", ("idx-test-1",)).fetchone()
    conn.close()
    assert row is not None
    assert row["domain"] == "article"

    # Verify target store row was written
    rows = stores.query("test-articles", "SELECT * FROM articles WHERE index_id = ?", ("idx-test-1",))
    assert len(rows) == 1
    assert rows[0]["title"] == "Hello"
