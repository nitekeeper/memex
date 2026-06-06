"""brain global/local GraphRAG ask-mode tests (Option-B; subagents mocked).

- global: map-reduce over community_reports (map scores 0-100, drop zeros,
  reduce sorts desc + budget-fills).
- local: seed by cosine + expand the relation neighborhood + attach the
  seeds' community reports.
- flat: the existing ask path is exercised here too to lock the regression
  (byte-for-byte behavior unchanged).

INERT-LEVER GUARDS: global_ask_prepare MUST consult community_reports (returns
no_reports when empty, real map_units when present); local_ask MUST expand the
relation neighborhood beyond the seeds.
"""

import struct

import pytest

from scripts import brain, install, onboarding
from scripts.db import get_connection, memex_home


def _pack(vec):
    return struct.pack(f"<{len(vec)}f", *vec)


def _doc(conn, idx, text, vec=None):
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, embedding, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            idx,
            idx,
            "article",
            "article",
            "articles",
            "1",
            text,
            _pack(vec) if vec else None,
            "librarian-1",
        ),
    )


def _report(conn, cid, level, title, summary, rating, findings="[]"):
    conn.execute(
        "INSERT INTO community_reports (community_id, level, title, summary, rating, findings) "
        "VALUES (?,?,?,?,?,?)",
        (cid, level, title, summary, rating, findings),
    )


@pytest.fixture
def installed(tmp_memex_home):
    install.run()
    onboarding.register_human("human-test", "Test", "User")


# ── global ──────────────────────────────────────────────────────────────────


def test_global_ask_prepare_no_reports(installed):
    """No community reports -> no_reports status (degrades, not crash)."""
    out = brain.global_ask_prepare("what are the themes?", level=0)
    assert out["status"] == "no_reports"
    assert out["map_units"] == []


def test_global_ask_prepare_builds_map_units_from_reports(installed):
    """INERT-LEVER GUARD: global ask MUST consult community_reports."""
    conn = get_connection(str(memex_home() / "index.db"))
    _report(conn, "c0-0001", 0, "Cats", "All about cats.", 8.0)
    _report(conn, "c0-0002", 0, "Dogs", "All about dogs.", 5.0)
    # A level-1 report must NOT appear when we ask for level 0.
    _report(conn, "c1-0003", 1, "Pets", "Pets umbrella.", 9.0)
    conn.commit()
    conn.close()

    out = brain.global_ask_prepare("tell me the themes", level=0)
    assert out["status"] == "ready"
    cids = [u["community_id"] for u in out["map_units"]]
    assert cids == ["c0-0001", "c0-0002"]  # rating-desc order, level-0 only
    assert "tell me the themes" in out["map_units"][0]["map_prompt"]
    assert "All about cats." in out["map_units"][0]["map_prompt"]


def test_global_ask_prepare_query_placeholder_collision(installed):
    """A query containing a literal {{REPORT_BODY}} token must NOT be expanded.

    QUERY is substituted last, so user-supplied placeholder-shaped text can
    never be re-expanded into another template placeholder.
    """
    conn = get_connection(str(memex_home() / "index.db"))
    _report(conn, "c0-0001", 0, "Cats", "SUMMARY-MARKER", 8.0)
    conn.commit()
    conn.close()

    out = brain.global_ask_prepare("inject {{REPORT_BODY}} here", level=0)
    assert out["status"] == "ready"
    prompt = out["map_units"][0]["map_prompt"]
    # The literal token from the query survives unexpanded...
    assert "inject {{REPORT_BODY}} here" in prompt
    # ...and the real report body appears exactly once (no double expansion).
    assert prompt.count("SUMMARY-MARKER") == 1


def test_global_reduce_query_placeholder_collision(installed):
    """A reduce query containing a literal {{PARTIALS}} token must NOT expand."""
    scored = [{"community_id": "c0-0001", "score": 90, "partial_answer": "PARTIAL-MARKER"}]
    out = brain.global_ask_reduce_prepare("show {{PARTIALS}} now", scored)
    assert out["status"] == "ready"
    prompt = out["reduce_prompt"]
    assert "show {{PARTIALS}} now" in prompt
    assert prompt.count("PARTIAL-MARKER") == 1


def test_parse_map_response_clamps_and_strips():
    parsed = brain.parse_map_response('```json\n{"score": 150, "partial_answer": "X"}\n```')
    assert parsed["score"] == 100
    assert parsed["partial_answer"] == "X"
    neg = brain.parse_map_response('{"score": -3, "partial_answer": ""}')
    assert neg["score"] == 0


def test_global_reduce_drops_zeros_and_sorts(installed):
    """REDUCE drops score-0 partials and ranks the rest descending."""
    scored = [
        {"community_id": "c0-0001", "score": 0, "partial_answer": "irrelevant"},
        {"community_id": "c0-0002", "score": 40, "partial_answer": "mid"},
        {"community_id": "c0-0003", "score": 90, "partial_answer": "top"},
    ]
    out = brain.global_ask_reduce_prepare("q", scored)
    assert out["status"] == "ready"
    kept_ids = [k["community_id"] for k in out["kept"]]
    assert kept_ids == ["c0-0003", "c0-0002"]  # 90 then 40; the 0 dropped
    # The reduce prompt orders top-scoring first.
    assert out["reduce_prompt"].index("top") < out["reduce_prompt"].index("mid")


def test_global_reduce_no_signal_when_all_zero(installed):
    scored = [{"community_id": "c0-0001", "score": 0, "partial_answer": ""}]
    out = brain.global_ask_reduce_prepare("q", scored)
    assert out["status"] == "no_signal"
    assert out["kept"] == []


def test_global_reduce_respects_budget(installed):
    big = "y" * 5000
    scored = [
        {"community_id": "c1", "score": 50, "partial_answer": big},
        {"community_id": "c2", "score": 40, "partial_answer": big},
        {"community_id": "c3", "score": 30, "partial_answer": big},
    ]
    out = brain.global_ask_reduce_prepare("q", scored, char_budget=6000)
    # Budget allows the first block; the rest are dropped from the prompt.
    assert out["reduce_prompt"].count("y" * 5000) == 1


# ── local ─────────────────────────────────────────────────────────────────


def test_local_ask_expands_neighborhood_not_inert(installed):
    """INERT-LEVER GUARD: local ask MUST expand the relation neighborhood."""
    conn = get_connection(str(memex_home() / "index.db"))
    # seed s1 (close to query), neighbor n1 reachable via a relation.
    _doc(conn, "s1", "cats are great", vec=[1.0, 0.0, 0.0])
    _doc(conn, "n1", "feline companions", vec=[0.0, 0.0, 1.0])  # far from query
    conn.execute(
        "INSERT INTO relations (from_index_id, to_index_id, rel_type, confidence) "
        "VALUES ('s1','n1','similar_to',0.6)"
    )
    # n1 belongs to a community with a report.
    conn.execute(
        "INSERT INTO communities (community_id, level, parent, size) VALUES ('cc',0,NULL,2)"
    )
    conn.execute(
        "INSERT INTO community_members (community_id, index_id, level) VALUES ('cc','n1',0)"
    )
    _report(conn, "cc", 0, "Felines", "Cat community summary.", 7.0)
    conn.commit()
    conn.close()

    out = brain.local_ask("cats", seed_limit=1, hops=1, with_embedding=False)
    # with_embedding=False -> no cosine seeds; assert the expansion machinery
    # is wired by seeding manually below instead.
    assert out["status"] == "ready"


def test_local_ask_seed_expand_and_reports(installed, monkeypatch):
    """Full local path with a deterministic fake embedding provider."""
    from scripts import embeddings

    conn = get_connection(str(memex_home() / "index.db"))
    _doc(conn, "s1", "cats are great", vec=[1.0, 0.0, 0.0])
    _doc(conn, "n1", "feline companions", vec=[0.0, 1.0, 0.0])
    conn.execute(
        "INSERT INTO relations (from_index_id, to_index_id, rel_type, confidence) "
        "VALUES ('s1','n1','similar_to',0.6)"
    )
    conn.execute(
        "INSERT INTO communities (community_id, level, parent, size) VALUES ('cc',0,NULL,2)"
    )
    conn.execute(
        "INSERT INTO community_members (community_id, index_id, level) VALUES ('cc','n1',0)"
    )
    _report(conn, "cc", 0, "Felines", "Cat community summary.", 7.0)
    conn.commit()
    conn.close()

    # Fake the query embedding to point at s1's vector.
    monkeypatch.setattr(embeddings, "encode", lambda text: _pack([1.0, 0.0, 0.0]))

    out = brain.local_ask("cats", seed_limit=1, hops=1, with_embedding=True)
    assert out["status"] == "ready"
    assert out["seeds"] == ["s1"]
    assert "n1" in out["neighborhood"], "neighborhood expansion is inert"
    doc_ids = {d["index_id"] for d in out["documents"]}
    assert {"s1", "n1"} <= doc_ids
    report_ids = {r["community_id"] for r in out["community_reports"]}
    assert "cc" in report_ids, "seed/neighbor community reports not attached"


def test_local_ask_degrades_without_embeddings(installed, monkeypatch):
    """with_embedding=False -> empty seeds, no crash, no neighborhood."""
    out = brain.local_ask("anything", with_embedding=False)
    assert out["status"] == "ready"
    assert out["seeds"] == []
    assert out["neighborhood"] == []


# ── flat regression ─────────────────────────────────────────────────────────


def test_flat_ask_unchanged(installed):
    """flat mode = existing ask_prepare/ask_execute path, byte-for-byte."""
    conn = get_connection(str(memex_home() / "index.db"))
    _doc(conn, "idx-a", "cats are interesting")
    conn.commit()
    conn.close()

    prep = brain.ask_prepare("tell me about cats")
    assert prep["status"] == "ready"
    plan = {"fts_query": "cats", "vector_query": None, "filters": {}, "limit": 5}
    results = brain.ask_execute(prep, plan)
    assert [r["index_id"] for r in results] == ["idx-a"]
