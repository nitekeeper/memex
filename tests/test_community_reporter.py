"""community_reporter tests — bottom-up report generation (Option-B).

The Community Reporter subagent's LLM output is faked by passing a synthetic
JSON report straight to parse_report/report_complete (mirrors
test_brain_synthesize.py's mock pattern).

INERT-LEVER GUARD: a report MUST land in community_reports for a real
community; report_complete persisting nothing would be caught here.
"""

import json

import pytest

from scripts import communities
from scripts.agents import community_reporter
from scripts.db import get_connection, memex_home


def _doc(conn, idx, text):
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (idx, idx, "article", "article", "articles", "1", text, "librarian-1"),
    )


def _edge(conn, a, b, w=1.0):
    conn.execute(
        "INSERT OR REPLACE INTO relations (from_index_id, to_index_id, rel_type, confidence) "
        "VALUES (?, ?, ?, ?)",
        (a, b, "similar_to", w),
    )


@pytest.fixture
def community_present(bootstrapped_home):
    """One detected community of three connected docs."""
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    _doc(conn, "d1", "alpha beta gamma topic one")
    _doc(conn, "d2", "alpha beta topic one variant")
    _doc(conn, "d3", "gamma delta topic one tail")
    _edge(conn, "d1", "d2")
    _edge(conn, "d2", "d3")
    _edge(conn, "d1", "d3")
    conn.commit()
    conn.close()
    communities.detect_communities()
    # Resolve the single community id.
    conn = get_connection(index_db)
    cid = conn.execute("SELECT community_id FROM communities LIMIT 1").fetchone()["community_id"]
    conn.close()
    return index_db, cid


def test_report_prepare_builds_prompt_with_members(community_present):
    _index_db, cid = community_present
    prep = community_reporter.report_prepare(cid)
    assert prep["status"] == "ready"
    assert set(prep["member_index_ids"]) == {"d1", "d2", "d3"}
    # Member text is in the prompt.
    assert "topic one" in prep["subagent_prompt"]
    assert cid in prep["subagent_prompt"]


def test_report_complete_persists(community_present):
    """INERT-LEVER GUARD: a parsed report MUST be persisted."""
    index_db, cid = community_present
    prep = community_reporter.report_prepare(cid)
    report = {
        "title": "Topic One Cluster",
        "summary": "Three documents about topic one.",
        "rating": 6.5,
        "findings": [{"summary": "shared theme", "explanation": "all mention topic one"}],
    }
    result = community_reporter.report_complete(prep, report, embedding=None)
    assert result["status"] == "reported"
    assert result["community_id"] == cid

    conn = get_connection(index_db)
    row = conn.execute(
        "SELECT title, summary, rating, findings FROM community_reports WHERE community_id = ?",
        (cid,),
    ).fetchone()
    conn.close()
    assert row is not None, "report did not persist — community-report shipped inert"
    assert row["title"] == "Topic One Cluster"
    assert row["rating"] == 6.5
    assert json.loads(row["findings"])[0]["summary"] == "shared theme"


def test_report_complete_upserts(community_present):
    index_db, cid = community_present
    prep = community_reporter.report_prepare(cid)
    base = {
        "title": "v1",
        "summary": "first",
        "rating": 1.0,
        "findings": [{"summary": "s", "explanation": "e"}],
    }
    community_reporter.report_complete(prep, base)
    base2 = {**base, "title": "v2", "summary": "second"}
    community_reporter.report_complete(prep, base2)
    conn = get_connection(index_db)
    rows = conn.execute(
        "SELECT title FROM community_reports WHERE community_id = ?", (cid,)
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["title"] == "v2"


def test_parse_report_validates_and_clamps_rating():
    raw = json.dumps(
        {
            "title": "T",
            "summary": "S",
            "rating": 99,  # out of range -> clamps to 10
            "findings": [{"summary": "a", "explanation": "b"}],
        }
    )
    parsed = community_reporter.parse_report(raw)
    assert parsed["rating"] == 10.0
    assert parsed["title"] == "T"


def test_parse_report_strips_code_fence():
    raw = '```json\n{"title":"T","summary":"S","rating":5,"findings":[]}\n```'
    parsed = community_reporter.parse_report(raw)
    assert parsed["summary"] == "S"


def test_parse_report_rejects_missing_fields():
    with pytest.raises(ValueError):
        community_reporter.parse_report('{"title": "x"}')


def test_report_prepare_budget_truncates_and_uses_child_reports(bootstrapped_home):
    """When raw member text overflows the budget and child reports exist,
    child-report summaries substitute (bottom-up roll-up)."""
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    # Parent community with a child that already has a report.
    conn.execute(
        "INSERT INTO communities (community_id, level, parent, size) VALUES (?,?,?,?)",
        ("parent", 0, None, 2),
    )
    conn.execute(
        "INSERT INTO communities (community_id, level, parent, size) VALUES (?,?,?,?)",
        ("child", 1, "parent", 1),
    )
    # Two big member docs under parent so the budget overflows.
    big = "x" * 6000
    _doc(conn, "m1", big)
    _doc(conn, "m2", big)
    conn.execute(
        "INSERT INTO community_members (community_id, index_id, level) VALUES (?,?,?)",
        ("parent", "m1", 0),
    )
    conn.execute(
        "INSERT INTO community_members (community_id, index_id, level) VALUES (?,?,?)",
        ("parent", "m2", 0),
    )
    _edge(conn, "m1", "m2")
    # Child report exists.
    conn.execute(
        "INSERT INTO community_reports (community_id, level, title, summary, rating, findings) "
        "VALUES (?,?,?,?,?,?)",
        ("child", 1, "Child Title", "child rollup summary", 4.0, "[]"),
    )
    conn.commit()
    conn.close()

    prep = community_reporter.report_prepare("parent", char_budget=8000)
    assert prep["truncated"] is True
    assert prep["used_child_reports"] is True
    assert "child rollup summary" in prep["subagent_prompt"]


def test_report_complete_tolerates_embedding_unavailable(community_present):
    """The skill embeds the summary but may catch EmbeddingUnavailable; passing
    embedding=None must persist a report with NULL embedding, no crash."""
    index_db, cid = community_present
    prep = community_reporter.report_prepare(cid)
    report = {
        "title": "T",
        "summary": "S",
        "rating": 3.0,
        "findings": [],
    }
    # Simulate the skill's degraded path: encode raised, caller passes None.
    community_reporter.report_complete(prep, report, embedding=None)
    conn = get_connection(index_db)
    row = conn.execute(
        "SELECT embedding FROM community_reports WHERE community_id = ?", (cid,)
    ).fetchone()
    conn.close()
    assert row["embedding"] is None


def test_stale_community_ids_lists_report_less(community_present):
    _index_db, cid = community_present
    stale = community_reporter.stale_community_ids()
    assert cid in stale
    # After reporting, it drops out.
    prep = community_reporter.report_prepare(cid)
    community_reporter.report_complete(
        prep,
        {"title": "t", "summary": "s", "rating": 1.0, "findings": []},
    )
    assert cid not in community_reporter.stale_community_ids()


def test_stale_community_ids_ordered_deepest_first(bootstrapped_home):
    """Bottom-up: deeper (higher-level-number) communities come first."""
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    conn.execute(
        "INSERT INTO communities (community_id, level, parent, size) VALUES ('root',0,NULL,2)"
    )
    conn.execute(
        "INSERT INTO communities (community_id, level, parent, size) VALUES ('leaf',1,'root',1)"
    )
    conn.commit()
    conn.close()
    stale = community_reporter.stale_community_ids()
    assert stale.index("leaf") < stale.index("root")
