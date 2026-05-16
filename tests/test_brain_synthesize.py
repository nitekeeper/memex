import json
import pytest
from unittest.mock import patch
from scripts import install, brain, onboarding, stores
from scripts.db import memex_home, get_connection


@pytest.fixture
def installed_with_human_and_sources(tmp_memex_home):
    install.run()
    onboarding.register_human("human-test", "Test", "User")

    # Seed two article rows and matching index entries
    conn = get_connection(str(memex_home() / "index.db"))
    for idx, body in [("idx-s1", "first source body"), ("idx-s2", "second source body")]:
        conn.execute(
            "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (idx, idx, "article", "article", "articles", "1", body, "librarian-1"),
        )
    conn.commit()
    conn.close()


def test_synthesize_writes_to_syntheses_table(installed_with_human_and_sources):
    mock_synthesis = "Combined view: both sources discuss bodies."
    mock_lib = json.dumps({
        "index_id": "idx-syn-1",
        "key": "synthesis-1",
        "domain": "synthesis",
        "searchable": "synthesis text",
        "metadata": {},
        "relations": [
            {"to_index_id": "idx-s1", "rel_type": "synthesizes"},
            {"to_index_id": "idx-s2", "rel_type": "synthesizes"},
        ]
    })
    with patch("scripts.brain._invoke_synthesizer", return_value=mock_synthesis), \
         patch("scripts.agents.librarian._invoke_llm", return_value=mock_lib), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00\x00\x00\x00"):
        result = brain.synthesize(
            topic="bodies",
            input_index_ids=["idx-s1", "idx-s2"],
            caller_agent_id="human-test",
        )

    rows = stores.query("article", "SELECT * FROM syntheses WHERE index_id = ?", (result["index_id"],))
    assert len(rows) == 1
    assert rows[0]["body"] == mock_synthesis
    assert rows[0]["topic"] == "bodies"
    assert json.loads(rows[0]["inputs_json"]) == ["idx-s1", "idx-s2"]
