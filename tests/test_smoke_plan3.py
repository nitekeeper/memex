"""Plan-3 Brain end-to-end smoke — Phase 1 (ingest + capture + lint).

Phase 1 of the Option-B refactor covers ingest and capture via the
prepare/complete pair. ask() and synthesize() are deferred to Phase 2
(Reference Librarian) and Phase 3 (Synthesizer) respectively. Those
parts of the lifecycle stay xfailed until those phases land.
"""

from pathlib import Path

from scripts import brain, install, onboarding


def test_e2e_brain_lifecycle_phase1(tmp_memex_home):
    """install -> onboard -> ingest_prepare/complete x2 -> capture_prepare/complete -> lint."""
    install.run()
    onboarding.register_human("human-test", "Test", "User")

    # 1. Ingest two articles (synthetic Librarian output stands in for the
    #    Task-tool subagent dispatch).
    prep1 = brain.ingest_prepare("First", "first body", "human-test", source_url="https://a")
    r1 = brain.ingest_complete(
        prep1,
        {
            "index_id": "idx-a1",
            "key": "first-article",
            "domain": "article",
            "searchable": "first body",
            "metadata": {},
            "relations": [],
        },
    )
    assert r1["index_id"] == "idx-a1"

    prep2 = brain.ingest_prepare("Second", "second body", "human-test", source_url="https://b")
    r2 = brain.ingest_complete(
        prep2,
        {
            "index_id": "idx-a2",
            "key": "second-article",
            "domain": "article",
            "searchable": "second body",
            "metadata": {},
            "relations": [],
        },
    )
    assert r2["index_id"] == "idx-a2"

    # 2. Capture a free-form note
    cap_prep = brain.capture_prepare("captured thought", "human-test")
    c = brain.capture_complete(
        cap_prep,
        {
            "index_id": "idx-c1",
            "key": "capture-1",
            "domain": "capture",
            "searchable": "captured thought",
            "metadata": {},
            "relations": [],
        },
    )
    assert c["index_id"] == "idx-c1"

    # 3. Lint (no LLM — Data Steward audit)
    report = brain.lint()
    assert Path(report).exists()


def test_e2e_brain_ask(tmp_memex_home):
    """Phase-2 path: ask_prepare → synthetic query plan → ask_execute."""
    install.run()
    onboarding.register_human("human-test", "Test", "User")

    # Seed an index entry directly (bypassing the ingest LLM dispatch — that's
    # covered in test_e2e_brain_lifecycle_phase1).
    from scripts.db import get_connection, memex_home

    conn = get_connection(str(memex_home() / "index.db"))
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "idx-cat",
            "cats",
            "article",
            "article",
            "articles",
            "1",
            "cats are fascinating creatures",
            "librarian-1",
        ),
    )
    conn.commit()
    conn.close()

    prep = brain.ask_prepare("tell me about cats")
    synthetic_plan = {
        "fts_query": "cats",
        "vector_query": None,
        "filters": {},
        "limit": 5,
    }
    results = brain.ask_execute(prep, synthetic_plan)
    ids = {r["index_id"] for r in results}
    assert "idx-cat" in ids


def test_e2e_brain_synthesize(tmp_memex_home):
    """Phase-3 path: synthesize_prepare → (Synthesizer Task) → librarian.build_prompt
    → (Librarian Task) → synthesize_complete. Both LLM calls faked here."""
    from scripts import stores
    from scripts.db import get_connection, memex_home

    install.run()
    onboarding.register_human("human-test", "Test", "User")

    # Seed two source articles
    for idx, body in [("idx-src-1", "first src"), ("idx-src-2", "second src")]:
        stores.insert(
            "article",
            "articles",
            {
                "index_id": idx,
                "title": idx,
                "body": body,
                "source_url": None,
                "source_hash": f"h-{idx}",
                "raw_path": "",
                "created_by": "human-test",
            },
        )
        conn = get_connection(str(memex_home() / "index.db"))
        conn.execute(
            "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
            "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (idx, idx, "article", "article", "articles", "1", body, "librarian-1"),
        )
        conn.commit()
        conn.close()

    prep = brain.synthesize_prepare(
        topic="srcs",
        input_index_ids=["idx-src-1", "idx-src-2"],
        caller_agent_id="human-test",
    )
    assert prep["status"] == "ready"

    # Synthesizer subagent would produce this — faked.
    synthesis_body = "Both sources discuss srcs."

    # Librarian subagent would classify the synthesis — faked.
    librarian_output = {
        "index_id": "idx-syn-smoke",
        "key": "smoke-synthesis",
        "domain": "synthesis",
        "searchable": "smoke synthesis",
        "metadata": {},
        "relations": [],
    }

    result = brain.synthesize_complete(
        prepare_result=prep,
        synthesis_body=synthesis_body,
        librarian_output=librarian_output,
    )
    assert result["status"] == "synthesized"
    assert result["index_id"] == "idx-syn-smoke"

    # The synthesis row landed in article.db.syntheses
    rows = stores.query(
        "article",
        "SELECT * FROM syntheses WHERE index_id = ?",
        ("idx-syn-smoke",),
    )
    assert len(rows) == 1
    assert rows[0]["body"] == synthesis_body

    # Auto-added synthesizes relations
    conn = get_connection(str(memex_home() / "index.db"))
    rels = {
        (r["to_index_id"], r["rel_type"])
        for r in conn.execute(
            "SELECT to_index_id, rel_type FROM relations WHERE from_index_id = ?",
            ("idx-syn-smoke",),
        )
    }
    conn.close()
    assert ("idx-src-1", "synthesizes") in rels
    assert ("idx-src-2", "synthesizes") in rels
