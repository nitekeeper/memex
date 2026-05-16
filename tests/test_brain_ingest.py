"""brain.ingest_prepare / ingest_complete tests — Option B (Task-tool dispatch).

The Librarian subagent's role is faked here by passing synthetic JSON to
ingest_complete. The two-step API mirrors the skill markdown's
prepare → Task dispatch → complete recipe.
"""
import hashlib
import pytest
from scripts import install, brain, onboarding, stores
from scripts.db import memex_home


@pytest.fixture
def installed_with_human(tmp_memex_home):
    install.run()
    onboarding.register_human("human-test", "Test", "User")
    return memex_home()


def _ingest(title, body, caller_agent_id, librarian_output, source_url=None, embedding=None):
    """Test helper: run the full prep + complete cycle with synthetic LLM output."""
    prep = brain.ingest_prepare(title, body, caller_agent_id, source_url=source_url)
    if prep["status"] == "skipped":
        return prep
    return brain.ingest_complete(prep, librarian_output, embedding=embedding)


def test_ingest_prepare_returns_subagent_prompt_for_new_article(installed_with_human):
    prep = brain.ingest_prepare(
        title="X", body="hello world", caller_agent_id="human-test",
    )
    assert prep["status"] == "ready"
    assert prep["target_store"] == "article"
    assert prep["target_table"] == "articles"
    assert "subagent_prompt" in prep
    assert "hello world" in prep["subagent_prompt"]
    assert "Ranganathan" in prep["subagent_prompt"]  # librarian profile embedded
    # Raw archive happened
    assert prep["raw_archive"]["hash"] == hashlib.sha256(b"hello world").hexdigest()


def test_ingest_complete_writes_to_article_db(installed_with_human):
    librarian_output = {
        "index_id": "idx-1",
        "key": "test-article",
        "domain": "article",
        "searchable": "test searchable",
        "metadata": {},
        "relations": [],
    }
    result = _ingest(
        title="Test Article", body="this is the body",
        caller_agent_id="human-test", librarian_output=librarian_output,
        source_url="https://example.com/a",
        embedding=b"\x00\x00\x00\x00",
    )
    assert result["status"] == "ingested"
    rows = stores.query(
        "article", "SELECT * FROM articles WHERE index_id = ?", (result["index_id"],),
    )
    assert len(rows) == 1
    assert rows[0]["title"] == "Test Article"
    assert rows[0]["source_url"] == "https://example.com/a"


def test_ingest_records_source_hash(installed_with_human):
    librarian_output = {
        "index_id": "idx-1", "key": "k", "domain": "article",
        "searchable": "s", "metadata": {}, "relations": [],
    }
    result = _ingest(
        title="X", body="hello", caller_agent_id="human-test",
        librarian_output=librarian_output, source_url="https://x",
    )
    rows = stores.query(
        "article", "SELECT source_hash FROM articles WHERE index_id = ?",
        (result["index_id"],),
    )
    assert rows[0]["source_hash"] == hashlib.sha256(b"hello").hexdigest()


def test_ingest_prepare_returns_skipped_on_duplicate_content(installed_with_human):
    """Re-ingest of the same canonical body is a no-op at the prepare step."""
    librarian_output = {
        "index_id": "idx-1", "key": "k", "domain": "article",
        "searchable": "s", "metadata": {}, "relations": [],
    }
    r1 = _ingest(
        title="X", body="hello", caller_agent_id="human-test",
        librarian_output=librarian_output, source_url="https://x",
    )
    # Second prepare-call detects the source_hash and returns "skipped" —
    # no subagent dispatch needed.
    r2_prep = brain.ingest_prepare(
        title="X", body="hello", caller_agent_id="human-test",
        source_url="https://x",
    )
    assert r2_prep["status"] == "skipped"
    assert r2_prep["existing_index_id"] == r1["index_id"]


def test_ingest_different_content_creates_new_row(installed_with_human):
    """Different canonical body → fresh prepare + new row, no skip."""
    output_a = {
        "index_id": "idx-a", "key": "k", "domain": "article",
        "searchable": "s", "metadata": {}, "relations": [],
    }
    output_b = {
        "index_id": "idx-b", "key": "k", "domain": "article",
        "searchable": "s", "metadata": {}, "relations": [],
    }
    r1 = _ingest(title="X", body="version 1", caller_agent_id="human-test",
                 librarian_output=output_a, source_url="https://x")
    r2 = _ingest(title="X", body="version 2", caller_agent_id="human-test",
                 librarian_output=output_b, source_url="https://x")
    assert r1["index_id"] == "idx-a"
    assert r2["index_id"] == "idx-b"
    assert r2["status"] == "ingested"


def test_ingest_complete_refuses_non_ready_prepare(installed_with_human):
    """ingest_complete must reject a prepare result that's not status=ready."""
    fake_skipped = {"status": "skipped", "existing_index_id": "idx-x"}
    with pytest.raises(ValueError):
        brain.ingest_complete(
            fake_skipped,
            {"index_id": "y", "key": "k", "domain": "article", "searchable": "s"},
        )
