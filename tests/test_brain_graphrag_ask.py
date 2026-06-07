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

import os
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


# ── prompt-cache prefix determinism (cache-reuse levers) ─────────────────────


def test_global_map_stable_rubric_leads_and_is_byte_identical_across_units(installed):
    """Anti-revert (AI-1): the stable scoring rubric + JSON schema must lead.

    The harness auto-caches a request PREFIX. For the many per-report MAP
    dispatches in one global ask to reuse that cache, every map_prompt MUST
    open with a byte-identical stable instruction/rubric/schema block, with
    the only divergence being the per-unit report body (and the query) which
    TRAIL. If the template is reverted to rubric-trailing, the longest common
    prefix shrinks below the schema and this test fails.
    """
    conn = get_connection(str(memex_home() / "index.db"))
    # Distinct bodies so the prompts DO diverge in their variable region.
    _report(conn, "c0-0001", 0, "Cats", "BODY-ALPHA about cats.", 8.0)
    _report(conn, "c0-0002", 0, "Dogs", "BODY-BETA about dogs.", 5.0)
    conn.commit()
    conn.close()

    out = brain.global_ask_prepare("WHAT-IS-THE-QUERY", level=0)
    assert out["status"] == "ready"
    p0 = out["map_units"][0]["map_prompt"]
    p1 = out["map_units"][1]["map_prompt"]
    assert p0 != p1  # they must diverge somewhere (per-unit body differs)

    # (a) The byte-identical shared prefix contains the full stable rubric.
    common = os.path.commonprefix([p0, p1])
    assert "## Task" in common
    assert '"score"' in common
    assert '"partial_answer"' in common
    assert "Output ONLY the JSON object" in common

    # (b) The first divergence occurs AFTER the schema text — i.e. the variable
    #     part is the per-unit report body, not the rubric. (commonprefix length
    #     == the index of the first differing byte.)
    divergence = len(common)
    schema_end = p0.index("Output ONLY the JSON object")
    assert schema_end < divergence, (
        "schema must be inside the shared prefix; divergence must trail it"
    )

    # (c) The user-controlled QUERY trails the divergence point (injection-safe
    #     AND cache-safe: variable user input is LAST).
    assert "WHAT-IS-THE-QUERY" in p0
    assert p0.index("WHAT-IS-THE-QUERY") > divergence


def test_global_reduce_stable_rubric_leads(installed):
    """Anti-revert (AI-2): the stable synthesis rubric must lead the REDUCE prompt.

    The stable instructions + ## Task + output-format rule must appear BEFORE
    the variable {{PARTIALS}} block and BEFORE the query. If reverted to
    rubric-trailing, the rubric would land after the partials and this fails.
    """
    scored = [
        {"community_id": "c0-0007", "score": 90, "partial_answer": "PARTIAL-MARKER"},
    ]
    out = brain.global_ask_reduce_prepare("REDUCE-QUERY-MARKER", scored)
    assert out["status"] == "ready"
    prompt = out["reduce_prompt"]

    task_idx = prompt.index("## Task")
    output_rule_idx = prompt.index("Output the answer as prose only")
    partials_idx = prompt.index("c0-0007")  # a {{PARTIALS}}-derived marker
    query_idx = prompt.index("REDUCE-QUERY-MARKER")

    # Stable rubric leads the variable partials block...
    assert task_idx < partials_idx
    assert output_rule_idx < partials_idx
    # ...and the partials lead the query (query trails, injection-safe).
    assert partials_idx < query_idx


# ── local ─────────────────────────────────────────────────────────────────


def test_local_ask_key_free_seed_expand_and_reports(installed):
    """KEY-FREE GUARD: the DEFAULT local path seeds via FTS5 — no provider.

    No embedding column is populated and no embeddings.encode is called; the
    seed is found by lexical FTS5 match, then the neighborhood expands over
    `relations` and the seed/neighbor community report is attached.
    """
    conn = get_connection(str(memex_home() / "index.db"))
    # Text-only docs (embedding=NULL). s1 matches the query lexically.
    _doc(conn, "s1", "cats are great")
    _doc(conn, "n1", "feline companions")  # reachable only via the relation
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

    # Default path: with_embedding defaults to False -> NO provider needed.
    out = brain.local_ask("cats", seed_limit=1, hops=1)
    assert out["status"] == "ready"
    assert out["seeds"] == ["s1"], "FTS5 seed did not find the lexical match"
    assert "n1" in out["neighborhood"], "neighborhood expansion is inert"
    doc_ids = {d["index_id"] for d in out["documents"]}
    assert {"s1", "n1"} <= doc_ids
    report_ids = {r["community_id"] for r in out["community_reports"]}
    assert "cc" in report_ids, "seed/neighbor community reports not attached"


def test_local_ask_default_never_raises_embedding_unavailable(installed, monkeypatch):
    """The default local path MUST NOT touch the embedding provider at all.

    Even if encode() would blow up (no key), local_ask must return useful seeds
    via FTS5. We poison encode to guarantee it's never called on the default
    path.
    """
    from scripts import embeddings

    def _boom(_text):
        raise embeddings.EmbeddingUnavailable("not_configured", "openai", "no key")

    monkeypatch.setattr(embeddings, "encode", _boom)

    conn = get_connection(str(memex_home() / "index.db"))
    _doc(conn, "s1", "cats are great")
    conn.commit()
    conn.close()

    out = brain.local_ask("cats")  # default with_embedding=False
    assert out["status"] == "ready"
    assert out["seeds"] == ["s1"]


def test_local_ask_optional_embedding_booster(installed, monkeypatch):
    """with_embedding=True remains an opt-in cosine booster (flat-ask parity)."""
    from scripts import embeddings

    conn = get_connection(str(memex_home() / "index.db"))
    _doc(conn, "s1", "cats are great", vec=[1.0, 0.0, 0.0])
    _doc(conn, "n1", "feline companions", vec=[0.0, 1.0, 0.0])
    conn.commit()
    conn.close()

    monkeypatch.setattr(embeddings, "encode", lambda text: _pack([1.0, 0.0, 0.0]))

    out = brain.local_ask("cats", seed_limit=1, hops=1, with_embedding=True)
    assert out["status"] == "ready"
    assert out["seeds"] == ["s1"]


def test_local_ask_degrades_on_empty_corpus(installed):
    """No matching docs -> empty seeds, no crash, no neighborhood (key-free)."""
    out = brain.local_ask("nothing-matches-this-query")
    assert out["status"] == "ready"
    assert out["seeds"] == []
    assert out["neighborhood"] == []


# ── GraphRAG end-to-end, NO embedding provider ──────────────────────────────


def test_graphrag_pipeline_runs_with_no_embedding_provider(installed, monkeypatch):
    """E2E GUARD: graph_build -> detect_communities -> report prep -> global/local
    all run with NO embedding provider configured.

    Unset every provider env var and poison embeddings.encode so any embedding
    dependency on the GraphRAG path would raise. The whole pipeline must still
    produce edges, communities, report prep units, and ask context.
    """
    from scripts import communities, embeddings, graph_build
    from scripts.agents import community_reporter

    # No provider whatsoever.
    for var in ("MEMEX_EMBEDDING_PROVIDER", "OPENAI_API_KEY", "VOYAGE_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    def _boom(_text):
        raise embeddings.EmbeddingUnavailable("not_configured", "openai", "no key")

    monkeypatch.setattr(embeddings, "encode", _boom)

    # Seed a text-rich, two-cluster corpus (embedding=NULL throughout).
    conn = get_connection(str(memex_home() / "index.db"))
    for i in range(3):
        _doc(conn, f"cat{i}", f"cats feline whiskers purr kitten note{i}")
    for i in range(3):
        _doc(conn, f"dog{i}", f"dogs canine bark puppy leash note{i}")
    conn.commit()
    conn.close()

    # 1. Lexical graph population — must produce real edges, key-free.
    g = graph_build.build_graph()
    assert g["considered"] == 6
    assert g["edges_written"] > 0, "GraphRAG inert: no edges with no provider"

    # 2. Community detection over the fresh similar_to edges.
    c = communities.detect_communities()
    assert c["communities"] >= 1

    # 3. Report prep for a stale community (Python-only; no LLM, no embedding).
    stale = community_reporter.stale_community_ids()
    assert stale, "no communities to report on"
    prep = community_reporter.report_prepare(stale[0])
    assert prep["status"] == "ready"

    # 4. local ask (default key-free FTS5 seed) returns context, no raise.
    local = brain.local_ask("cats", seed_limit=2, hops=1)
    assert local["status"] == "ready"
    assert local["seeds"], "FTS5 seed empty with no provider"

    # 5. global ask prepare reads community_reports (none yet) -> graceful.
    glob = brain.global_ask_prepare("themes?", level=0)
    assert glob["status"] in {"ready", "no_reports"}


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
