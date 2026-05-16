import json
import pytest
from unittest.mock import patch
from scripts import install, brain, onboarding, stores


def test_e2e_full_brain_lifecycle(tmp_memex_home):
    """install → onboard → ingest → ask → capture → synthesize → lint."""
    install.run()
    onboarding.register_human("human-test", "Test", "User")

    mock_lib_responses = iter([
        json.dumps({"index_id": "idx-a1", "key": "first-article", "domain": "article", "searchable": "first body", "metadata": {}, "relations": []}),
        json.dumps({"index_id": "idx-a2", "key": "second-article", "domain": "article", "searchable": "second body", "metadata": {}, "relations": []}),
        json.dumps({"index_id": "idx-c1", "key": "capture-1", "domain": "capture", "searchable": "captured thought", "metadata": {}, "relations": []}),
        json.dumps({"index_id": "idx-syn", "key": "synthesis-1", "domain": "synthesis", "searchable": "synthesis text", "metadata": {}, "relations": []}),
    ])

    with patch("scripts.agents.librarian._invoke_llm", side_effect=lambda p: next(mock_lib_responses)), \
         patch("scripts.agents.librarian._encode_embedding", return_value=b"\x00\x00\x00\x00"), \
         patch("scripts.agents.reference_librarian._invoke_llm",
               return_value=json.dumps({"fts_query": "body", "vector_query": None, "filters": {}, "limit": 10})), \
         patch("scripts.brain._invoke_synthesizer", return_value="Synthesized view of both sources."):

        # 1. Ingest two articles
        r1 = brain.ingest("First", "first body", "human-test", source_url="https://a")
        r2 = brain.ingest("Second", "second body", "human-test", source_url="https://b")
        assert r1["index_id"] == "idx-a1"
        assert r2["index_id"] == "idx-a2"

        # 2. Ask
        results = brain.ask("body")
        ids = {r["index_id"] for r in results}
        assert "idx-a1" in ids or "idx-a2" in ids

        # 3. Capture
        c = brain.capture("captured thought", "human-test")
        assert c["index_id"] == "idx-c1"

        # 4. Synthesize
        s = brain.synthesize(topic="bodies", input_index_ids=["idx-a1", "idx-a2"], caller_agent_id="human-test")
        assert s["index_id"] == "idx-syn"

        # 5. Lint
        report = brain.lint()
        from pathlib import Path
        assert Path(report).exists()
