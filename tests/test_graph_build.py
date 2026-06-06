"""graph_build tests — the k-NN graph population step (GraphRAG seed).

INERT-LEVER GUARD: the central contract is that build_graph produces real
`similar_to` edges on a seeded fixture. If a future change silently neutered
graph population (or the relation graph stayed empty), test_build_graph_*
would go RED — the feature cannot ship inert.
"""

import struct

import pytest

from scripts import graph_build
from scripts.db import get_connection, memex_home


def _pack(vec):
    return struct.pack(f"<{len(vec)}f", *vec)


def _insert_doc(conn, idx, vec, searchable="x"):
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, embedding, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (idx, idx, "article", "article", "articles", "1", searchable, _pack(vec), "librarian-1"),
    )


@pytest.fixture
def seeded_two_clusters(bootstrapped_home):
    """Six embedded docs forming two clear cosine clusters in 3-D."""
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    # Cluster A near [1,0,0]; cluster B near [0,1,0]. Distinct enough that
    # within-cluster cosine ~1.0 and cross-cluster cosine ~0.0.
    cluster_a = {
        "a1": [1.0, 0.0, 0.0],
        "a2": [0.98, 0.05, 0.0],
        "a3": [0.95, 0.10, 0.02],
    }
    cluster_b = {
        "b1": [0.0, 1.0, 0.0],
        "b2": [0.05, 0.98, 0.0],
        "b3": [0.02, 0.95, 0.10],
    }
    for idx, vec in {**cluster_a, **cluster_b}.items():
        _insert_doc(conn, idx, vec)
    conn.commit()
    conn.close()
    return index_db


def test_build_graph_produces_edges_not_inert(seeded_two_clusters):
    """INERT-LEVER GUARD: a seeded two-cluster fixture MUST yield >0 edges."""
    result = graph_build.build_graph()
    assert result["considered"] == 6
    assert result["edges_written"] > 0, "graph_build shipped inert — zero similar_to edges"

    conn = get_connection(seeded_two_clusters)
    rows = conn.execute(
        "SELECT from_index_id, to_index_id, rel_type, confidence FROM relations "
        "WHERE rel_type = 'similar_to'"
    ).fetchall()
    conn.close()
    assert len(rows) > 0
    # Edges carry the cosine as confidence.
    for r in rows:
        assert r["rel_type"] == "similar_to"
        assert 0.5 <= r["confidence"] <= 1.0001


def test_build_graph_respects_threshold(seeded_two_clusters):
    """With a high threshold, only within-cluster (near-1.0) edges survive;
    cross-cluster pairs (cosine ~0) are excluded."""
    graph_build.build_graph(threshold=0.9)
    conn = get_connection(seeded_two_clusters)
    rows = conn.execute(
        "SELECT from_index_id, to_index_id FROM relations WHERE rel_type='similar_to'"
    ).fetchall()
    conn.close()
    a_nodes = {"a1", "a2", "a3"}
    for r in rows:
        # No edge should bridge the two clusters at threshold 0.9.
        assert (r["from_index_id"] in a_nodes) == (r["to_index_id"] in a_nodes)


def test_build_graph_respects_k(seeded_two_clusters):
    """k caps out-degree per node."""
    graph_build.build_graph(k=1, threshold=0.0)
    conn = get_connection(seeded_two_clusters)
    rows = conn.execute(
        "SELECT from_index_id, COUNT(*) AS n FROM relations "
        "WHERE rel_type='similar_to' GROUP BY from_index_id"
    ).fetchall()
    conn.close()
    for r in rows:
        assert r["n"] <= 1


def test_build_graph_idempotent(seeded_two_clusters):
    """Re-running converges (no edge accumulation)."""
    r1 = graph_build.build_graph()
    r2 = graph_build.build_graph()
    assert r1["edges_written"] == r2["edges_written"]
    conn = get_connection(seeded_two_clusters)
    n = conn.execute("SELECT COUNT(*) AS n FROM relations WHERE rel_type='similar_to'").fetchone()[
        "n"
    ]
    conn.close()
    assert n == r2["edges_written"]


def test_build_graph_preserves_semantic_edges(seeded_two_clusters):
    """A rebuild must NOT clobber Librarian-authored (non-similar_to) edges."""
    conn = get_connection(seeded_two_clusters)
    conn.execute(
        "INSERT INTO relations (from_index_id, to_index_id, rel_type) VALUES (?, ?, ?)",
        ("a1", "b1", "cites"),
    )
    conn.commit()
    conn.close()

    graph_build.build_graph()

    conn = get_connection(seeded_two_clusters)
    cites = conn.execute("SELECT COUNT(*) AS n FROM relations WHERE rel_type='cites'").fetchone()[
        "n"
    ]
    conn.close()
    assert cites == 1, "graph_build clobbered a semantic edge"


def test_build_graph_degrades_on_too_few_docs(bootstrapped_home):
    """<2 embedded docs -> no edges, no crash."""
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    _insert_doc(conn, "solo", [1.0, 0.0, 0.0])
    conn.commit()
    conn.close()
    result = graph_build.build_graph()
    assert result["edges_written"] == 0


def test_build_graph_degrades_on_no_embeddings(bootstrapped_home):
    """Docs without embeddings -> no-op, no crash."""
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("noemb", "noemb", "article", "article", "articles", "1", "x", "librarian-1"),
    )
    conn.commit()
    conn.close()
    result = graph_build.build_graph()
    assert result["considered"] == 0
    assert result["edges_written"] == 0
