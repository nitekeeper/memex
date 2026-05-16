"""brain.synthesize_prepare / synthesize_complete tests — Phase 3 (Option-B).

Synthesize involves two subagent dispatches:
  1. Synthesizer → produces synthesis prose
  2. Librarian → classifies the synthesis as a new document

Tests fake both LLM outputs and verify the deterministic pieces:
- prep fetches the right sources and builds the Synthesizer prompt
- complete auto-adds `synthesizes` relations for each input_index_id
- complete persists to article.db.syntheses + Index
"""

import json

import pytest

from scripts import brain, install, onboarding, stores
from scripts.db import get_connection, memex_home


@pytest.fixture
def installed_with_two_sources(tmp_memex_home):
    install.run()
    onboarding.register_human("human-test", "Test", "User")

    # Seed two articles with matching index entries.
    index_db = str(memex_home() / "index.db")

    for idx, title, body in [
        ("idx-s1", "First Source", "first source body"),
        ("idx-s2", "Second Source", "second source body"),
    ]:
        # Article row
        stores.insert(
            "article",
            "articles",
            {
                "index_id": idx,
                "title": title,
                "body": body,
                "source_url": f"https://example.com/{idx}",
                "source_hash": f"hash-{idx}",
                "raw_path": f"/tmp/{idx}.md",
                "created_by": "human-test",
            },
        )
        # Index row
        conn = get_connection(index_db)
        conn.execute(
            "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
            "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (idx, idx, "article", "article", "articles", "1", body, "librarian-1"),
        )
        conn.commit()
        conn.close()


def test_synthesize_prepare_returns_synthesizer_prompt(installed_with_two_sources):
    prep = brain.synthesize_prepare(
        topic="bodies",
        input_index_ids=["idx-s1", "idx-s2"],
        caller_agent_id="human-test",
    )
    assert prep["status"] == "ready"
    assert prep["topic"] == "bodies"
    assert prep["input_index_ids"] == ["idx-s1", "idx-s2"]
    assert len(prep["sources"]) == 2
    assert "synthesizer_prompt" in prep
    # Both source bodies should appear in the prompt
    assert "first source body" in prep["synthesizer_prompt"]
    assert "second source body" in prep["synthesizer_prompt"]
    assert "bodies" in prep["synthesizer_prompt"]


def test_synthesize_prepare_drops_missing_sources(tmp_memex_home):
    """If an index_id doesn't resolve to a row in article.db.articles,
    it's silently omitted from the Synthesizer's input (the prompt only
    sees real source bodies)."""
    install.run()
    onboarding.register_human("human-test", "Test", "User")
    prep = brain.synthesize_prepare(
        topic="x",
        input_index_ids=["does-not-exist"],
        caller_agent_id="human-test",
    )
    assert prep["sources"] == []


def test_synthesize_complete_persists_synthesis(installed_with_two_sources):
    prep = brain.synthesize_prepare(
        topic="bodies",
        input_index_ids=["idx-s1", "idx-s2"],
        caller_agent_id="human-test",
    )
    synthesis_body = "Combined view: both sources discuss bodies."
    librarian_output = {
        "index_id": "idx-syn-1",
        "key": "synthesis-bodies",
        "domain": "synthesis",
        "searchable": "synthesis text",
        "metadata": {},
        "relations": [],
    }
    result = brain.synthesize_complete(
        prepare_result=prep,
        synthesis_body=synthesis_body,
        librarian_output=librarian_output,
    )
    assert result["status"] == "synthesized"
    assert result["index_id"] == "idx-syn-1"

    rows = stores.query(
        "article",
        "SELECT * FROM syntheses WHERE index_id = ?",
        (result["index_id"],),
    )
    assert len(rows) == 1
    assert rows[0]["body"] == synthesis_body
    assert rows[0]["topic"] == "bodies"
    assert json.loads(rows[0]["inputs_json"]) == ["idx-s1", "idx-s2"]


def test_synthesize_complete_auto_adds_synthesizes_relations(installed_with_two_sources):
    """synthesize_complete must add one `synthesizes` relation per input_index_id,
    regardless of what the Librarian returned. These are deterministic — the
    skill knows the inputs by construction."""
    prep = brain.synthesize_prepare(
        topic="bodies",
        input_index_ids=["idx-s1", "idx-s2"],
        caller_agent_id="human-test",
    )
    librarian_output = {
        "index_id": "idx-syn-1",
        "key": "k",
        "domain": "synthesis",
        "searchable": "s",
        "metadata": {},
        "relations": [],  # Librarian didn't tag any relations
    }
    brain.synthesize_complete(
        prepare_result=prep,
        synthesis_body="text",
        librarian_output=librarian_output,
    )

    # Both `synthesizes` edges should be in index.db.relations
    conn = get_connection(str(memex_home() / "index.db"))
    rels = conn.execute(
        "SELECT to_index_id, rel_type FROM relations WHERE from_index_id = ?",
        ("idx-syn-1",),
    ).fetchall()
    conn.close()

    edge_set = {(r["to_index_id"], r["rel_type"]) for r in rels}
    assert ("idx-s1", "synthesizes") in edge_set
    assert ("idx-s2", "synthesizes") in edge_set


def test_synthesize_complete_preserves_librarian_relations(installed_with_two_sources):
    """When the Librarian DOES tag additional relations (e.g., the synthesis
    cites an unrelated document), synthesize_complete preserves them alongside
    the auto-added synthesizes edges."""
    # First seed a third document the synthesis will reference
    conn = get_connection(str(memex_home() / "index.db"))
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "idx-other",
            "other",
            "article",
            "article",
            "articles",
            "99",
            "other reference",
            "librarian-1",
        ),
    )
    conn.commit()
    conn.close()

    prep = brain.synthesize_prepare(
        topic="x",
        input_index_ids=["idx-s1"],
        caller_agent_id="human-test",
    )
    librarian_output = {
        "index_id": "idx-syn-2",
        "key": "k",
        "domain": "synthesis",
        "searchable": "s",
        "metadata": {},
        "relations": [
            {"to_index_id": "idx-other", "rel_type": "references"},
        ],
    }
    brain.synthesize_complete(
        prepare_result=prep,
        synthesis_body="text",
        librarian_output=librarian_output,
    )

    conn = get_connection(str(memex_home() / "index.db"))
    rels = conn.execute(
        "SELECT to_index_id, rel_type FROM relations WHERE from_index_id = ?",
        ("idx-syn-2",),
    ).fetchall()
    conn.close()
    edge_set = {(r["to_index_id"], r["rel_type"]) for r in rels}
    assert ("idx-s1", "synthesizes") in edge_set  # auto-added
    assert ("idx-other", "references") in edge_set  # from Librarian


def test_synthesize_complete_refuses_non_ready_prepare():
    bad_prep = {"status": "error"}
    with pytest.raises(ValueError):
        brain.synthesize_complete(
            prepare_result=bad_prep,
            synthesis_body="t",
            librarian_output={
                "index_id": "x",
                "key": "k",
                "domain": "s",
                "searchable": "s",
            },
        )
