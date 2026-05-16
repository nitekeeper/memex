import json
import hashlib
import pytest
from unittest.mock import patch
from scripts import install, brain, onboarding, stores
from scripts.db import memex_home


@pytest.fixture
def installed_with_human(tmp_memex_home):
    install.run()
    onboarding.register_human("human-test", "Test", "User")
    return memex_home()


def test_ingest_new_article_writes_to_article_db(installed_with_human):
    mock_lib = json.dumps({
        "index_id": "idx-1",
        "key": "test-article",
        "domain": "article",
        "searchable": "test searchable",
        "metadata": {},
        "relations": []
    })
    with patch("scripts.agents.librarian._invoke_llm", return_value=mock_lib), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00\x00\x00\x00"):
        result = brain.ingest(
            title="Test Article",
            body="this is the body",
            source_url="https://example.com/a",
            caller_agent_id="human-test",
        )

    rows = stores.query("article", "SELECT * FROM articles WHERE index_id = ?", (result["index_id"],))
    assert len(rows) == 1
    assert rows[0]["title"] == "Test Article"
    assert rows[0]["source_url"] == "https://example.com/a"


def test_ingest_computes_source_hash(installed_with_human):
    mock_lib = json.dumps({
        "index_id": "idx-1",
        "key": "k",
        "domain": "article",
        "searchable": "s",
        "metadata": {},
        "relations": []
    })
    with patch("scripts.agents.librarian._invoke_llm", return_value=mock_lib), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00\x00\x00\x00"):
        result = brain.ingest(
            title="X", body="hello", source_url="https://x", caller_agent_id="human-test",
        )

    rows = stores.query("article", "SELECT source_hash FROM articles WHERE index_id = ?", (result["index_id"],))
    assert rows[0]["source_hash"] is not None
    expected = hashlib.sha256(b"hello").hexdigest()
    assert rows[0]["source_hash"] == expected


def test_ingest_rerun_with_same_content_returns_skipped(installed_with_human):
    """Re-ingest of the same canonical content is a no-op."""
    mock_lib = json.dumps({
        "index_id": "idx-1", "key": "k", "domain": "article",
        "searchable": "s", "metadata": {}, "relations": []
    })
    with patch("scripts.agents.librarian._invoke_llm", return_value=mock_lib), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00\x00\x00\x00"):
        r1 = brain.ingest(title="X", body="hello", source_url="https://x", caller_agent_id="human-test")
        r2 = brain.ingest(title="X", body="hello", source_url="https://x", caller_agent_id="human-test")

    assert r2["status"] == "skipped"
    assert r2["existing_index_id"] == r1["index_id"]


def test_ingest_rerun_with_different_content_creates_new_row(installed_with_human):
    """Different content → new row (no in-place merge per spec)."""
    responses = [
        json.dumps({"index_id": "idx-a", "key": "k", "domain": "article", "searchable": "s", "metadata": {}, "relations": []}),
        json.dumps({"index_id": "idx-b", "key": "k", "domain": "article", "searchable": "s", "metadata": {}, "relations": []}),
    ]
    call_count = {"n": 0}
    def mock_llm(prompt):
        r = responses[call_count["n"]]
        call_count["n"] += 1
        return r

    with patch("scripts.agents.librarian._invoke_llm", side_effect=mock_llm), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00\x00\x00\x00"):
        r1 = brain.ingest(title="X", body="version 1", source_url="https://x", caller_agent_id="human-test")
        r2 = brain.ingest(title="X", body="version 2", source_url="https://x", caller_agent_id="human-test")

    assert r1["index_id"] != r2["index_id"]
    assert r2["status"] == "ingested"
