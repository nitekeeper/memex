"""code_graph ingest + query behavior tests.

Covers the required contract:
  - basic ingest counts
  - IDEMPOTENCY / duplicate-edge regression (the anti-graphify-non-idempotent-
    merge guard — re-ingest must NOT accumulate rows)
  - fragment upsert (changed label updates in place, no duplicate)
  - invalidation on file delete (nodes + owned edges + inbound edges; no dangling)
  - invalidation on symbol rename (old id + its inbound edges gone, new id present)
  - query correctness (where_is / callers / dependencies / neighbors / module_map)
    in deterministic order
  - multi-repo isolation (queries scoped by repo identity don't bleed)

Uses bootstrapped_home so code_graph.db resolves under an isolated ~/.memex/.
"""

from scripts import code_graph

REPO = "owner/repo"


def _graph():
    """A small two-file graphify-shaped graph.

    foo.py owns: foo_main (calls bar_util, imports os_mod)
    bar.py owns: bar_util, os_mod
    A cross-file edge foo_main --calls--> bar_util (target owned by bar.py).
    Uses the new `links` edge-array key.
    """
    return {
        "nodes": [
            {
                "id": "foo:foo_main",
                "label": "foo_main",
                "file_type": "py",
                "source_file": "foo.py",
                "source_location": "foo.py:1",
            },
            {
                "id": "bar:bar_util",
                "label": "bar_util",
                "file_type": "py",
                "source_file": "bar.py",
                "source_location": "bar.py:1",
            },
            {
                "id": "bar:os_mod",
                "label": "os_mod",
                "file_type": "py",
                "source_file": "bar.py",
                "source_location": "bar.py:5",
            },
        ],
        "links": [
            {
                "source": "foo:foo_main",
                "target": "bar:bar_util",
                "relation": "calls",
                "confidence": "high",
                "confidence_score": 0.9,
                "weight": 1.0,
                "source_file": "foo.py",
                "source_location": "foo.py:2",
                "context": "foo_main() -> bar_util()",
            },
            {
                "source": "foo:foo_main",
                "target": "bar:os_mod",
                "relation": "imports",
                "source_file": "foo.py",
                "source_location": "foo.py:0",
            },
            {
                "source": "bar:bar_util",
                "target": "bar:os_mod",
                "relation": "uses",
                "source_file": "bar.py",
                "source_location": "bar.py:2",
            },
        ],
    }


def _count(table, repo=REPO):
    conn = code_graph._connect()
    try:
        return conn.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE repo = ?", (repo,)
        ).fetchone()["n"]
    finally:
        conn.close()


def test_ingest_counts(bootstrapped_home):
    summary = code_graph.ingest_graph(REPO, _graph())
    assert summary["nodes"] == 3
    assert summary["edges"] == 3
    assert summary["files"] == 2
    assert summary["repo"] == REPO


def test_ingest_accepts_legacy_edges_key(bootstrapped_home):
    g = _graph()
    g["edges"] = g.pop("links")  # older graphify output uses `edges`
    summary = code_graph.ingest_graph(REPO, g)
    assert summary["edges"] == 3


def test_ingest_idempotent_no_duplicate_edges(bootstrapped_home):
    """ANTI-GRAPHIFY-NON-IDEMPOTENT-MERGE GUARD.

    graphify's own update merges duplicate edges on every rerun
    (1459 -> 2765 -> 4071 -> 5377). memex's per-file fragment upsert must keep
    node AND edge counts IDENTICAL across repeated ingests of the same graph.
    """
    s1 = code_graph.ingest_graph(REPO, _graph())
    s2 = code_graph.ingest_graph(REPO, _graph())
    s3 = code_graph.ingest_graph(REPO, _graph())
    assert s1["nodes"] == s2["nodes"] == s3["nodes"] == 3
    assert s1["edges"] == s2["edges"] == s3["edges"] == 3
    assert _count("nodes") == 3
    assert _count("edges") == 3


def test_fragment_upsert_updates_label_in_place(bootstrapped_home):
    """Re-ingest one file's fragment with a changed label -> row updated, not
    duplicated."""
    code_graph.ingest_graph(REPO, _graph())
    conn = code_graph._connect()
    try:
        code_graph.ingest_fragment(
            conn,
            REPO,
            "foo.py",
            [
                {
                    "id": "foo:foo_main",
                    "label": "foo_main_RENAMED_LABEL",
                    "file_type": "py",
                    "source_file": "foo.py",
                    "source_location": "foo.py:1",
                }
            ],
            [
                {
                    "source": "foo:foo_main",
                    "target": "bar:bar_util",
                    "relation": "calls",
                    "source_file": "foo.py",
                }
            ],
        )
        conn.commit()
    finally:
        conn.close()
    # Same id count (no duplicate), label updated in place.
    assert _count("nodes") == 3
    rows = code_graph.where_is(REPO, "foo_main_RENAMED_LABEL")
    assert len(rows) == 1
    assert rows[0]["id"] == "foo:foo_main"


def test_invalidate_file_removes_nodes_owned_and_inbound_edges(bootstrapped_home):
    """invalidate_file on bar.py removes bar.py's nodes, its owned edges, AND
    inbound edges from foo.py pointing at bar.py's now-gone symbols. No dangling
    edges remain."""
    code_graph.ingest_graph(REPO, _graph())
    result = code_graph.invalidate_file(REPO, "bar.py")
    assert result["nodes_deleted"] == 2  # bar_util + os_mod
    # foo_main->bar_util (calls) and foo_main->bar:os_mod (imports) are inbound to bar.py.
    # Exact count (deterministic): catches an over-deletion regression that a loose
    # `>= 2` would silently pass (per the multi-mechanism exact-count discipline).
    assert result["inbound_edges_deleted"] == 2

    # Only foo.py's node survives; bar.py owned edge (uses) cascaded away.
    assert _count("nodes") == 1
    # No dangling edges: every remaining edge has both endpoints present.
    conn = code_graph._connect()
    try:
        dangling = conn.execute(
            "SELECT COUNT(*) AS n FROM edges e WHERE e.repo = ? AND ("
            "e.source NOT IN (SELECT id FROM nodes WHERE repo = ?) OR "
            "e.target NOT IN (SELECT id FROM nodes WHERE repo = ?))",
            (REPO, REPO, REPO),
        ).fetchone()["n"]
    finally:
        conn.close()
    assert dangling == 0


def test_invalidate_symbol_rename_drops_inbound_to_old_id(bootstrapped_home):
    """Rename a symbol in bar.py (old id gone, new id present). Re-ingesting the
    bar.py fragment drops the old node (cascade owned edges) and the inbound
    foo.py->old-id edge must be gone after a prune; the new id is present."""
    code_graph.ingest_graph(REPO, _graph())
    # Re-ingest bar.py with bar_util renamed to bar_helper (new id).
    conn = code_graph._connect()
    try:
        code_graph.ingest_fragment(
            conn,
            REPO,
            "bar.py",
            [
                {
                    "id": "bar:bar_helper",
                    "label": "bar_helper",
                    "source_file": "bar.py",
                    "source_location": "bar.py:1",
                },
                {
                    "id": "bar:os_mod",
                    "label": "os_mod",
                    "source_file": "bar.py",
                    "source_location": "bar.py:5",
                },
            ],
            [
                {
                    "source": "bar:bar_helper",
                    "target": "bar:os_mod",
                    "relation": "uses",
                    "source_file": "bar.py",
                }
            ],
        )
        conn.commit()
    finally:
        conn.close()
    # New id present, old id gone.
    assert code_graph.where_is(REPO, "bar_helper")
    assert not code_graph.where_is(REPO, "bar_util")
    # The stale inbound edge foo_main -> bar:bar_util is now dangling; sweep it.
    code_graph.prune_dangling_edges(REPO)
    conn = code_graph._connect()
    try:
        stale = conn.execute(
            "SELECT COUNT(*) AS n FROM edges WHERE repo = ? AND target = ?",
            (REPO, "bar:bar_util"),
        ).fetchone()["n"]
    finally:
        conn.close()
    assert stale == 0


def test_where_is_exact_before_substring(bootstrapped_home):
    code_graph.ingest_graph(REPO, _graph())
    # Add a node whose label contains "util" as substring but is not exact.
    conn = code_graph._connect()
    try:
        conn.execute(
            "INSERT INTO nodes (repo, id, label, source_file) VALUES (?, ?, ?, ?)",
            (REPO, "z:util_extra", "bar_util_extra", "z.py"),
        )
        conn.commit()
    finally:
        conn.close()
    rows = code_graph.where_is(REPO, "bar_util")
    # Exact match ("bar_util") ranks before the substring match.
    assert rows[0]["label"] == "bar_util"
    assert {r["label"] for r in rows} == {"bar_util", "bar_util_extra"}


def test_callers(bootstrapped_home):
    code_graph.ingest_graph(REPO, _graph())
    rows = code_graph.callers(REPO, "bar:bar_util")
    assert [r["id"] for r in rows] == ["foo:foo_main"]
    assert rows[0]["relation"] == "calls"
    # os_mod is imported, not called -> no callers.
    assert code_graph.callers(REPO, "bar:os_mod") == []


def test_dependencies(bootstrapped_home):
    code_graph.ingest_graph(REPO, _graph())
    rows = code_graph.dependencies(REPO, "foo:foo_main")
    # foo_main: calls bar_util + imports os_mod. Deterministic order by relation.
    rels = [(r["relation"], r["id"]) for r in rows]
    assert rels == [("calls", "bar:bar_util"), ("imports", "bar:os_mod")]


def test_neighbors_bounded_and_deterministic(bootstrapped_home):
    code_graph.ingest_graph(REPO, _graph())
    res = code_graph.neighbors(REPO, "foo:foo_main", depth=1)
    ids = {n["id"] for n in res["nodes"]}
    assert ids == {"foo:foo_main", "bar:bar_util", "bar:os_mod"}
    assert res["truncated"] is False
    # node list is sorted by id (deterministic)
    assert [n["id"] for n in res["nodes"]] == sorted(ids)


def test_neighbors_respects_max_nodes_cap(bootstrapped_home):
    code_graph.ingest_graph(REPO, _graph())
    res = code_graph.neighbors(REPO, "foo:foo_main", depth=2, max_nodes=1)
    # Cap of 1 means only the root survives the visited set.
    assert len(res["nodes"]) == 1
    assert res["truncated"] is True


def test_neighbors_relation_filter(bootstrapped_home):
    code_graph.ingest_graph(REPO, _graph())
    res = code_graph.neighbors(REPO, "foo:foo_main", relation="calls", depth=1)
    # Only the 'calls' edge is traversed -> bar_util reached, os_mod not.
    ids = {n["id"] for n in res["nodes"]}
    assert ids == {"foo:foo_main", "bar:bar_util"}


def test_module_map(bootstrapped_home):
    code_graph.ingest_graph(REPO, _graph())
    m = code_graph.module_map(REPO, "bar.py")
    node_ids = {n["id"] for n in m["nodes"]}
    assert node_ids == {"bar:bar_util", "bar:os_mod"}
    # intra: bar_util -> os_mod (uses). inter: foo_main -> bar_util / os_mod.
    intra = {(e["source"], e["target"], e["relation"]) for e in m["intra_edges"]}
    inter = {(e["source"], e["target"], e["relation"]) for e in m["inter_edges"]}
    assert ("bar:bar_util", "bar:os_mod", "uses") in intra
    assert ("foo:foo_main", "bar:bar_util", "calls") in inter
    assert ("foo:foo_main", "bar:os_mod", "imports") in inter


def test_multi_repo_isolation(bootstrapped_home):
    code_graph.ingest_graph(REPO, _graph())
    other = "owner/other"
    code_graph.ingest_graph(other, _graph())
    # Queries scoped by repo don't bleed.
    assert _count("nodes", REPO) == 3
    assert _count("nodes", other) == 3
    # Deleting one repo's file leaves the other untouched.
    code_graph.invalidate_file(REPO, "bar.py")
    assert _count("nodes", REPO) == 1
    assert _count("nodes", other) == 3
    assert {n["label"] for n in code_graph.where_is(other, "bar_util")} == {"bar_util"}
    assert code_graph.where_is(REPO, "bar_util") == []


def test_repo_status_and_needs_update(bootstrapped_home):
    code_graph.ingest_graph(REPO, _graph(), built_at_commit="abc123")
    status = code_graph.repo_status(REPO)
    assert status["built_at_commit"] == "abc123"
    assert status["needs_update"] == 0
    code_graph.set_needs_update(REPO, True)
    assert code_graph.repo_status(REPO)["needs_update"] == 1


def test_ingest_from_path_and_json_string(bootstrapped_home, tmp_path):
    import json

    p = tmp_path / "graph.json"
    p.write_text(json.dumps(_graph()), encoding="utf-8")
    assert code_graph.ingest_graph(REPO, p)["nodes"] == 3
    # raw JSON string also accepted
    code_graph.ingest_graph("o/json", json.dumps(_graph()))
    assert _count("nodes", "o/json") == 3
