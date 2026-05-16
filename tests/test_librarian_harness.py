"""Librarian harness tests — Option B (Task-tool subagent dispatch) refactor.

The Librarian runs as a Claude Code subagent (see spec §8.5); Python's role
is prep work, prompt construction, response parsing, and persistence. There
is no `_invoke_llm` to mock — tests feed synthetic JSON directly into
`write_entry()` to exercise the persistence half.
"""

import json

import pytest

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
        existing_index_snippet=[{"index_id": "x", "key": "prior-article", "domain": "article"}],
    )
    assert "prior-article" in prompt


def test_fetch_context_returns_profile_and_snippet(tmp_memex_home):
    from scripts import install

    install.run()
    ctx = librarian.fetch_context(target_store="article")
    assert "profile" in ctx
    assert "snippet" in ctx
    assert "target_store" in ctx
    assert ctx["target_store"] == "article"
    assert "Ranganathan" in ctx["profile"]
    assert isinstance(ctx["snippet"], list)


def test_parse_response_extracts_structured_output():
    mock_response = json.dumps(
        {
            "index_id": "idx-abc",
            "key": "test-key",
            "domain": "article",
            "searchable": "test searchable text",
            "metadata": {"author": "X"},
            "relations": [{"to_index_id": "idx-other", "rel_type": "cites"}],
        }
    )
    parsed = librarian.parse_response(mock_response)
    assert parsed["index_id"] == "idx-abc"
    assert parsed["domain"] == "article"
    assert parsed["relations"][0]["rel_type"] == "cites"


def test_parse_response_strips_markdown_code_fences():
    """Subagents often wrap JSON in ```json ... ```; parser must handle it."""
    fenced = (
        "```json\n"
        + json.dumps({"index_id": "x", "key": "k", "domain": "article", "searchable": "s"})
        + "\n```"
    )
    parsed = librarian.parse_response(fenced)
    assert parsed["index_id"] == "x"


def test_parse_response_raises_on_missing_required_field():
    bad_response = json.dumps({"index_id": "x"})  # missing domain, key, searchable
    with pytest.raises(ValueError):
        librarian.parse_response(bad_response)


def test_validate_output_accepts_caller_built_dict():
    """Consumers (e.g. Atelier) that build librarian_output deterministically
    must be able to validate it against the same schema parse_response uses."""
    out = librarian.validate_output(
        {
            "index_id": "idx-1",
            "key": "k",
            "domain": "task",
            "searchable": "title. body excerpt.",
        }
    )
    # Defaults are filled in
    assert out["metadata"] == {}
    assert out["relations"] == []
    # Required fields preserved
    assert out["index_id"] == "idx-1"
    assert out["domain"] == "task"


def test_validate_output_preserves_caller_metadata_and_relations():
    out = librarian.validate_output(
        {
            "index_id": "idx-2",
            "key": "k2",
            "domain": "task",
            "searchable": "s",
            "metadata": {"project_id": "atl-7"},
            "relations": [{"to_index_id": "idx-proj", "rel_type": "part_of"}],
        }
    )
    assert out["metadata"] == {"project_id": "atl-7"}
    assert out["relations"][0]["rel_type"] == "part_of"


def test_validate_output_raises_on_missing_fields():
    with pytest.raises(ValueError, match="missing fields"):
        librarian.validate_output({"index_id": "x", "key": "k"})  # missing domain, searchable


def test_validate_output_raises_on_non_dict():
    with pytest.raises(ValueError, match="must be a dict"):
        librarian.validate_output("not a dict")  # type: ignore[arg-type]


def test_validate_output_does_not_mutate_input():
    src = {"index_id": "x", "key": "k", "domain": "task", "searchable": "s"}
    librarian.validate_output(src)
    assert "metadata" not in src
    assert "relations" not in src


def test_write_entry_accepts_caller_built_librarian_output(tmp_memex_home, tmp_path):
    """The caller-built path (Atelier-style consumers): skip the subagent,
    pass a Python-constructed librarian_output to write_entry directly.

    Same persistence behavior as the subagent path — both go through
    librarian.write_entry, which is the single write surface."""
    from scripts import install, stores

    install.run()

    md = tmp_path / "m"
    md.mkdir()
    (md / "001.sql").write_text(
        "CREATE TABLE tasks ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "index_id TEXT NOT NULL UNIQUE, "
        "title TEXT NOT NULL, "
        "status TEXT NOT NULL"
        ");"
    )
    stores.create_store("atelier", str(tmp_path / "atelier.db"), str(md))

    # No subagent dispatch — caller builds the classification.
    caller_built = {
        "index_id": "task-001",
        "key": "ship-memex-v2",
        "domain": "task",
        "searchable": "Ship Memex v2. status=in_progress",
        "metadata": {"project_id": "memex"},
        "relations": [],
    }

    result = librarian.write_entry(
        payload={"title": "Ship Memex v2", "status": "in_progress"},
        librarian_output=caller_built,
        target_store="atelier",
        target_table="tasks",
        caller_agent_id="librarian-1",
    )

    assert result["index_id"] == "task-001"
    assert result["row_id"] is not None

    # Index row landed with the caller-supplied domain
    from scripts.db import get_connection, memex_home

    conn = get_connection(str(memex_home() / "index.db"))
    row = conn.execute(
        "SELECT domain, store, table_name FROM documents WHERE index_id = ?",
        ("task-001",),
    ).fetchone()
    conn.close()
    assert row["domain"] == "task"
    assert row["store"] == "atelier"
    assert row["table_name"] == "tasks"

    # Target store row landed
    rows = stores.query("atelier", "SELECT * FROM tasks WHERE index_id = ?", ("task-001",))
    assert rows[0]["status"] == "in_progress"


def test_write_entry_persists_to_index_and_target_store(tmp_memex_home, tmp_path):
    """Feed a synthetic Librarian output into write_entry and verify both
    index.db.documents and the target-store row land correctly."""
    from scripts import install, stores

    install.run()

    # Create a target store
    md = tmp_path / "m"
    md.mkdir()
    (md / "001.sql").write_text(
        "CREATE TABLE articles ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "index_id TEXT NOT NULL UNIQUE, "
        "title TEXT NOT NULL, "
        "body TEXT NOT NULL"
        ");"
    )
    stores.create_store("test-articles", str(tmp_path / "ta.db"), str(md))

    # Synthetic Librarian output (what a real subagent would return)
    librarian_output = {
        "index_id": "idx-test-1",
        "key": "hello-world",
        "domain": "article",
        "searchable": "hello world body content",
        "metadata": {"topic": "greeting"},
        "relations": [],
    }

    result = librarian.write_entry(
        payload={"title": "Hello", "body": "hello world body content"},
        librarian_output=librarian_output,
        target_store="test-articles",
        target_table="articles",
        caller_agent_id="librarian-1",
        embedding=b"\x00\x00\x00\x00",  # synthetic non-empty embedding
    )

    assert result["index_id"] == "idx-test-1"
    assert result["row_id"] is not None

    # Verify index.db row was written
    from scripts.db import get_connection, memex_home

    conn = get_connection(str(memex_home() / "index.db"))
    row = conn.execute("SELECT * FROM documents WHERE index_id = ?", ("idx-test-1",)).fetchone()
    conn.close()
    assert row is not None
    assert row["domain"] == "article"
    assert row["row_id"] == str(result["row_id"])

    # Verify target store row was written
    rows = stores.query(
        "test-articles", "SELECT * FROM articles WHERE index_id = ?", ("idx-test-1",)
    )
    assert len(rows) == 1
    assert rows[0]["title"] == "Hello"


def test_write_entry_works_without_embedding(tmp_memex_home, tmp_path):
    """v2.0 graceful degradation: if no OPENAI_API_KEY, skill passes
    embedding=None; FTS5 still works, vector cosine is skipped."""
    from scripts import install, stores

    install.run()

    md = tmp_path / "m"
    md.mkdir()
    (md / "001.sql").write_text(
        "CREATE TABLE articles ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "index_id TEXT NOT NULL UNIQUE, "
        "body TEXT NOT NULL"
        ");"
    )
    stores.create_store("noembed", str(tmp_path / "ne.db"), str(md))

    librarian_output = {
        "index_id": "idx-no-embed",
        "key": "k",
        "domain": "article",
        "searchable": "s",
        "metadata": {},
        "relations": [],
    }

    librarian.write_entry(
        payload={"body": "hello"},
        librarian_output=librarian_output,
        target_store="noembed",
        target_table="articles",
        caller_agent_id="librarian-1",
        embedding=None,
    )

    from scripts.db import get_connection, memex_home

    conn = get_connection(str(memex_home() / "index.db"))
    row = conn.execute(
        "SELECT embedding FROM documents WHERE index_id = ?", ("idx-no-embed",)
    ).fetchone()
    conn.close()
    assert row["embedding"] is None  # NULL in DB


def test_write_entry_records_relations(tmp_memex_home, tmp_path):
    from scripts import install, stores
    from scripts.db import get_connection, memex_home

    install.run()

    md = tmp_path / "m"
    md.mkdir()
    (md / "001.sql").write_text(
        "CREATE TABLE articles (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "index_id TEXT NOT NULL UNIQUE, body TEXT);"
    )
    stores.create_store("rels", str(tmp_path / "r.db"), str(md))

    # Insert a target doc that the new doc will cite
    target_output = {
        "index_id": "idx-target",
        "key": "t",
        "domain": "article",
        "searchable": "target",
        "metadata": {},
        "relations": [],
    }
    librarian.write_entry(
        payload={"body": "target body"},
        librarian_output=target_output,
        target_store="rels",
        target_table="articles",
        caller_agent_id="librarian-1",
    )

    # Now insert a doc that cites it
    citing_output = {
        "index_id": "idx-citing",
        "key": "c",
        "domain": "article",
        "searchable": "citing",
        "metadata": {},
        "relations": [{"to_index_id": "idx-target", "rel_type": "cites"}],
    }
    librarian.write_entry(
        payload={"body": "citing body"},
        librarian_output=citing_output,
        target_store="rels",
        target_table="articles",
        caller_agent_id="librarian-1",
    )

    conn = get_connection(str(memex_home() / "index.db"))
    rels = conn.execute(
        "SELECT * FROM relations WHERE from_index_id = ?", ("idx-citing",)
    ).fetchall()
    conn.close()
    assert len(rels) == 1
    assert rels[0]["to_index_id"] == "idx-target"
    assert rels[0]["rel_type"] == "cites"


def test_write_entry_raises_on_malformed_librarian_output():
    """If the subagent returns garbage (missing required fields),
    write_entry must refuse to persist."""
    bad_output = {"index_id": "x"}  # missing domain, key, searchable
    with pytest.raises(ValueError):
        librarian.write_entry(
            payload={"body": "x"},
            librarian_output=bad_output,
            target_store="article",
            target_table="articles",
            caller_agent_id="librarian-1",
        )
