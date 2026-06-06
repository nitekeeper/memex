"""communities tests — hierarchical greedy-modularity detection.

INERT-LEVER GUARD: detect_communities MUST separate an obvious two-cluster
graph into >=2 communities. A silent revert that produced one blob (or zero
communities) turns these RED.
"""

import pytest

from scripts import communities
from scripts.db import get_connection, memex_home


def _doc(conn, idx):
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (idx, idx, "article", "article", "articles", "1", f"text {idx}", "librarian-1"),
    )


def _edge(conn, a, b, w=1.0, rel="similar_to"):
    conn.execute(
        "INSERT OR REPLACE INTO relations (from_index_id, to_index_id, rel_type, confidence) "
        "VALUES (?, ?, ?, ?)",
        (a, b, rel, w),
    )


@pytest.fixture
def two_clique_graph(bootstrapped_home):
    """Two triangles (a1-a2-a3, b1-b2-b3) joined by a single weak bridge."""
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    for idx in ["a1", "a2", "a3", "b1", "b2", "b3"]:
        _doc(conn, idx)
    # Dense within clusters.
    for a, b in [("a1", "a2"), ("a2", "a3"), ("a1", "a3")]:
        _edge(conn, a, b, w=1.0)
    for a, b in [("b1", "b2"), ("b2", "b3"), ("b1", "b3")]:
        _edge(conn, a, b, w=1.0)
    # One weak bridge.
    _edge(conn, "a1", "b1", w=0.1)
    conn.commit()
    conn.close()
    return index_db


def test_detect_separates_two_clusters_not_inert(two_clique_graph):
    """INERT-LEVER GUARD: two obvious cliques -> exactly two level-0 communities."""
    result = communities.detect_communities()
    assert result["communities"] >= 2, "community detection shipped inert"

    conn = get_connection(two_clique_graph)
    rows = conn.execute(
        "SELECT cm.community_id, cm.index_id FROM community_members cm "
        "JOIN communities c ON c.community_id = cm.community_id WHERE c.level = 0"
    ).fetchall()
    conn.close()

    by_comm = {}
    for r in rows:
        by_comm.setdefault(r["community_id"], set()).add(r["index_id"])
    # The two triangles must land in different communities.
    comm_of = {idx: cid for cid, members in by_comm.items() for idx in members}
    assert comm_of["a1"] == comm_of["a2"] == comm_of["a3"]
    assert comm_of["b1"] == comm_of["b2"] == comm_of["b3"]
    assert comm_of["a1"] != comm_of["b1"]


def test_detect_deterministic(two_clique_graph):
    """Same graph -> identical partition across runs."""
    communities.detect_communities()
    conn = get_connection(two_clique_graph)
    first = sorted(
        (r["community_id"], r["index_id"])
        for r in conn.execute("SELECT community_id, index_id FROM community_members")
    )
    conn.close()

    communities.detect_communities()
    conn = get_connection(two_clique_graph)
    second = sorted(
        (r["community_id"], r["index_id"])
        for r in conn.execute("SELECT community_id, index_id FROM community_members")
    )
    conn.close()
    assert first == second


def test_detect_recurses_above_cap(bootstrapped_home):
    """A community above the size cap produces a deeper level + parent links.

    An 8-node clique is one community at level 0 (size 8 > cap 4). The floor-2
    recursion forces it to reveal a sub-split at level 1, so the hierarchy has
    >1 level and at least one community carries a parent link."""
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    nodes = [f"n{i}" for i in range(8)]
    for idx in nodes:
        _doc(conn, idx)
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            _edge(conn, nodes[i], nodes[j], w=1.0)
    conn.commit()
    conn.close()

    result = communities.detect_communities(size_cap=4)
    assert result["levels"] >= 2, f"expected hierarchy, got {result}"

    conn = get_connection(index_db)
    levels = {r["level"] for r in conn.execute("SELECT DISTINCT level FROM communities")}
    # There must be a level-0 root and at least one child carrying a parent.
    has_parent = conn.execute(
        "SELECT COUNT(*) AS n FROM communities WHERE parent IS NOT NULL"
    ).fetchone()["n"]
    # Parent links must reference real communities.
    orphan_parents = conn.execute(
        "SELECT COUNT(*) AS n FROM communities c WHERE c.parent IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM communities p WHERE p.community_id = c.parent)"
    ).fetchone()["n"]
    conn.close()
    assert 0 in levels
    assert 1 in levels
    assert has_parent > 0
    assert orphan_parents == 0


def test_detect_mece_per_level(two_clique_graph):
    """Each node appears at most once per level (MECE)."""
    communities.detect_communities()
    conn = get_connection(two_clique_graph)
    rows = conn.execute("SELECT index_id, level FROM community_members").fetchall()
    conn.close()
    seen = set()
    for r in rows:
        key = (r["index_id"], r["level"])
        assert key not in seen, f"node {r['index_id']} duplicated at level {r['level']}"
        seen.add(key)


def test_detect_degrades_on_empty_graph(bootstrapped_home):
    """No relations -> zero communities, no crash."""
    result = communities.detect_communities()
    assert result == {"levels": 0, "communities": 0, "members": 0, "nodes": 0}


def test_detect_drops_isolated_nodes(bootstrapped_home):
    """An edge-less node is not forced into a community at level 0."""
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    for idx in ["p1", "p2", "lonely"]:
        _doc(conn, idx)
    _edge(conn, "p1", "p2", w=1.0)
    conn.commit()
    conn.close()

    communities.detect_communities()
    conn = get_connection(index_db)
    placed = {r["index_id"] for r in conn.execute("SELECT index_id FROM community_members")}
    conn.close()
    assert "lonely" not in placed
    assert {"p1", "p2"} <= placed
