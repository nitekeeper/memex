"""brain.capture_prepare / capture_complete tests — Option B (Task-tool dispatch)."""
import pytest
from scripts import install, brain, onboarding, stores


@pytest.fixture
def installed_with_human(tmp_memex_home):
    install.run()
    onboarding.register_human("human-test", "Test", "User")


def test_capture_prepare_returns_subagent_prompt(installed_with_human):
    prep = brain.capture_prepare(
        body="quick thought about X", caller_agent_id="human-test",
    )
    assert prep["status"] == "ready"
    assert prep["target_store"] == "article"
    assert prep["target_table"] == "captures"
    assert "subagent_prompt" in prep
    assert "quick thought about X" in prep["subagent_prompt"]


def test_capture_complete_writes_to_captures_table(installed_with_human):
    prep = brain.capture_prepare(
        body="quick thought about X", caller_agent_id="human-test",
    )
    librarian_output = {
        "index_id": "idx-c1", "key": "k", "domain": "capture",
        "searchable": "s", "metadata": {}, "relations": [],
    }
    result = brain.capture_complete(prep, librarian_output)

    assert result["status"] == "captured"
    rows = stores.query(
        "article", "SELECT * FROM captures WHERE index_id = ?", (result["index_id"],),
    )
    assert len(rows) == 1
    assert rows[0]["body"] == "quick thought about X"


def test_capture_supports_optional_title(installed_with_human):
    prep = brain.capture_prepare(
        body="thought", caller_agent_id="human-test", title="My Thought",
    )
    librarian_output = {
        "index_id": "idx-c2", "key": "k", "domain": "capture",
        "searchable": "s", "metadata": {}, "relations": [],
    }
    result = brain.capture_complete(prep, librarian_output)
    rows = stores.query(
        "article", "SELECT * FROM captures WHERE index_id = ?", (result["index_id"],),
    )
    assert rows[0]["title"] == "My Thought"
