"""graph_build tests — the lexical k-NN graph population step (GraphRAG seed).

KEY-FREE GUARD: graph_build builds `similar_to` edges from document TEXT alone
(lexical Jaccard over `searchable`), with NO embedding provider and NO embedding
column populated. The fixtures below seed text-only docs (embedding=NULL) on
purpose — proving the GraphRAG seed step is both key-free AND live.

INERT-LEVER GUARD: the central contract is that build_graph produces real
`similar_to` edges on a text-only fixture. If a future change silently neutered
graph population (or re-introduced the embedding requirement so a no-provider
Brain produced zero edges), test_build_graph_* would go RED — the feature cannot
ship inert.
"""

from scripts import graph_build
from scripts.db import get_connection, memex_home


def _insert_doc(conn, idx, searchable):
    """Insert a TEXT-ONLY document — embedding is left NULL on purpose."""
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (idx, idx, "article", "article", "articles", "1", searchable, "librarian-1"),
    )


def _seed_two_clusters(conn):
    """Six text-only docs forming two clear lexical clusters.

    Cluster A shares cat vocabulary; cluster B shares dog vocabulary. Distinct
    enough that within-cluster Jaccard is high and cross-cluster overlap is ~0.
    """
    cluster_a = {
        "a1": "cats feline whiskers purr kitten",
        "a2": "cats feline whiskers purr tabby",
        "a3": "cats feline whiskers kitten tabby",
    }
    cluster_b = {
        "b1": "dogs canine bark puppy leash",
        "b2": "dogs canine bark puppy collar",
        "b3": "dogs canine bark leash collar",
    }
    for idx, text in {**cluster_a, **cluster_b}.items():
        _insert_doc(conn, idx, text)
    conn.commit()


def _make_seeded(bootstrapped_home):
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    _seed_two_clusters(conn)
    conn.close()
    return index_db


def test_build_graph_is_key_free_no_embeddings(bootstrapped_home):
    """KEY-FREE GUARD: text-only docs (NULL embeddings) MUST yield >0 edges.

    This proves graph_build needs NO embedding provider — it builds edges from
    `searchable` text alone. If the embedding requirement ever crept back, a
    no-provider Brain would produce zero edges and this would go RED.
    """
    index_db = _make_seeded(bootstrapped_home)

    # Confirm the precondition: NOT ONE document carries an embedding.
    conn = get_connection(index_db)
    embedded = conn.execute(
        "SELECT COUNT(*) AS n FROM documents WHERE embedding IS NOT NULL"
    ).fetchone()["n"]
    conn.close()
    assert embedded == 0, "fixture must be text-only — no embeddings"

    result = graph_build.build_graph()
    assert result["considered"] == 6
    assert result["edges_written"] > 0, "graph_build shipped inert on text-only docs"

    conn = get_connection(index_db)
    rows = conn.execute(
        "SELECT from_index_id, to_index_id, rel_type, confidence FROM relations "
        "WHERE rel_type = 'similar_to'"
    ).fetchall()
    conn.close()
    assert len(rows) > 0
    for r in rows:
        assert r["rel_type"] == "similar_to"
        assert 0.0 < r["confidence"] <= 1.0001


def test_build_graph_no_embeddings_import(bootstrapped_home):
    """ANTI-REGRESSION: graph_build must not import the embeddings module.

    Source-grep guard so the key-free property can't silently regress to an
    embedding-cosine requirement.
    """
    import inspect

    src = inspect.getsource(graph_build)
    # No embeddings import of any form, and no call to the cosine helper.
    assert "from scripts.embeddings" not in src
    assert "import embeddings" not in src
    assert "embeddings" not in graph_build.__dict__, "graph_build bound an embeddings symbol"
    # The cosine() call site (with a paren) must be gone — prose mentions OK.
    assert "cosine(" not in src


def test_build_graph_respects_threshold(bootstrapped_home):
    """With a high threshold, only within-cluster (high-overlap) edges survive;
    cross-cluster pairs (Jaccard ~0) are excluded."""
    index_db = _make_seeded(bootstrapped_home)
    graph_build.build_graph(threshold=0.3)
    conn = get_connection(index_db)
    rows = conn.execute(
        "SELECT from_index_id, to_index_id FROM relations WHERE rel_type='similar_to'"
    ).fetchall()
    conn.close()
    a_nodes = {"a1", "a2", "a3"}
    for r in rows:
        # No edge should bridge the two clusters at a high threshold.
        assert (r["from_index_id"] in a_nodes) == (r["to_index_id"] in a_nodes)


def test_build_graph_respects_k(bootstrapped_home):
    """k caps out-degree per node."""
    index_db = _make_seeded(bootstrapped_home)
    graph_build.build_graph(k=1, threshold=0.0)
    conn = get_connection(index_db)
    rows = conn.execute(
        "SELECT from_index_id, COUNT(*) AS n FROM relations "
        "WHERE rel_type='similar_to' GROUP BY from_index_id"
    ).fetchall()
    conn.close()
    for r in rows:
        assert r["n"] <= 1


def test_build_graph_idempotent(bootstrapped_home):
    """Re-running converges (no edge accumulation)."""
    index_db = _make_seeded(bootstrapped_home)
    r1 = graph_build.build_graph()
    r2 = graph_build.build_graph()
    assert r1["edges_written"] == r2["edges_written"]
    conn = get_connection(index_db)
    n = conn.execute("SELECT COUNT(*) AS n FROM relations WHERE rel_type='similar_to'").fetchone()[
        "n"
    ]
    conn.close()
    assert n == r2["edges_written"]


def test_build_graph_deterministic(bootstrapped_home):
    """DETERMINISM GUARD: re-run -> byte-identical edge set (same triples)."""
    index_db = _make_seeded(bootstrapped_home)

    def edge_set():
        conn = get_connection(index_db)
        rows = conn.execute(
            "SELECT from_index_id, to_index_id, confidence FROM relations "
            "WHERE rel_type='similar_to' ORDER BY from_index_id, to_index_id"
        ).fetchall()
        conn.close()
        return [(r["from_index_id"], r["to_index_id"], r["confidence"]) for r in rows]

    graph_build.build_graph()
    first = edge_set()
    graph_build.build_graph()
    second = edge_set()
    assert first == second
    assert len(first) > 0


def test_build_graph_preserves_semantic_edges(bootstrapped_home):
    """A rebuild must NOT clobber Librarian-authored (non-similar_to) edges."""
    index_db = _make_seeded(bootstrapped_home)
    conn = get_connection(index_db)
    conn.execute(
        "INSERT INTO relations (from_index_id, to_index_id, rel_type) VALUES (?, ?, ?)",
        ("a1", "b1", "cites"),
    )
    conn.commit()
    conn.close()

    graph_build.build_graph()

    conn = get_connection(index_db)
    cites = conn.execute("SELECT COUNT(*) AS n FROM relations WHERE rel_type='cites'").fetchone()[
        "n"
    ]
    conn.close()
    assert cites == 1, "graph_build clobbered a semantic edge"


def test_build_graph_degrades_on_too_few_docs(bootstrapped_home):
    """<2 docs with usable text -> no edges, no crash."""
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    _insert_doc(conn, "solo", "cats feline whiskers")
    conn.commit()
    conn.close()
    result = graph_build.build_graph()
    assert result["edges_written"] == 0


def test_build_graph_degrades_on_empty_text(bootstrapped_home):
    """Docs with no significant tokens -> no-op, no crash."""
    index_db = str(memex_home() / "index.db")
    conn = get_connection(index_db)
    # Stopwords + 1-char tokens only: tokenizer yields an empty set, so these
    # docs are not "considered".
    _insert_doc(conn, "e1", "the a an of to")
    _insert_doc(conn, "e2", "is it on or by")
    conn.commit()
    conn.close()
    result = graph_build.build_graph()
    assert result["considered"] == 0
    assert result["edges_written"] == 0
