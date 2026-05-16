import json
import pytest
from unittest.mock import patch
from scripts import install, brain, onboarding, stores


@pytest.fixture
def installed_with_human(tmp_memex_home):
    install.run()
    onboarding.register_human("human-test", "Test", "User")


def test_capture_writes_to_captures_table(installed_with_human):
    mock_lib = json.dumps({
        "index_id": "idx-c1",
        "key": "k",
        "domain": "capture",
        "searchable": "s",
        "metadata": {},
        "relations": []
    })
    with patch("scripts.agents.librarian._invoke_llm", return_value=mock_lib), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00\x00\x00\x00"):
        result = brain.capture(
            body="quick thought about X",
            caller_agent_id="human-test",
        )

    rows = stores.query("article", "SELECT * FROM captures WHERE index_id = ?", (result["index_id"],))
    assert len(rows) == 1
    assert rows[0]["body"] == "quick thought about X"


def test_capture_supports_optional_title(installed_with_human):
    mock_lib = json.dumps({
        "index_id": "idx-c2",
        "key": "k",
        "domain": "capture",
        "searchable": "s",
        "metadata": {},
        "relations": []
    })
    with patch("scripts.agents.librarian._invoke_llm", return_value=mock_lib), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00\x00\x00\x00"):
        result = brain.capture(
            body="thought",
            caller_agent_id="human-test",
            title="My Thought",
        )

    rows = stores.query("article", "SELECT * FROM captures WHERE index_id = ?", (result["index_id"],))
    assert rows[0]["title"] == "My Thought"
