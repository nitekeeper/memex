"""code_graph.sql schema tests — tables, columns, indexes, re-apply idempotency.

db/code_graph.sql is the self-contained schema for the SEPARATE code-navigation
graph store (~/.memex/code_graph.db). It is composed exclusively of re-entrant
`CREATE ... IF NOT EXISTS` statements so the install additive-reapply path can
re-run it on an existing store with no error.
"""

from pathlib import Path

DB_SQL = Path("db/code_graph.sql")


def _apply(conn):
    conn.executescript(DB_SQL.read_text(encoding="utf-8"))
    conn.commit()


def _table_columns(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _indexes(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA index_list({table})")}


def test_tables_exist(conn):
    _apply(conn)
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"repos", "nodes", "edges"} <= tables


def test_repos_columns(conn):
    _apply(conn)
    cols = _table_columns(conn, "repos")
    assert cols == {"repo", "built_at_commit", "needs_update", "updated_at", "schema_version"}


def test_nodes_columns(conn):
    _apply(conn)
    cols = _table_columns(conn, "nodes")
    assert cols == {"repo", "id", "label", "file_type", "source_file", "source_location"}


def test_edges_columns(conn):
    _apply(conn)
    cols = _table_columns(conn, "edges")
    assert cols == {
        "repo",
        "source",
        "target",
        "relation",
        "confidence",
        "confidence_score",
        "weight",
        "source_file",
        "source_location",
        "context",
    }


def test_expected_indexes_present(conn):
    _apply(conn)
    idx = _indexes(conn, "edges") | _indexes(conn, "nodes")
    for name in (
        "idx_cg_edges_target",
        "idx_cg_edges_source",
        "idx_cg_nodes_srcfile",
        "idx_cg_edges_srcfile",
        "idx_cg_nodes_label",
    ):
        assert name in idx, f"missing index {name}"


def test_reapply_is_idempotent(conn):
    """The install additive path re-applies code_graph.sql; double-apply must
    not raise (every statement is IF NOT EXISTS)."""
    _apply(conn)
    _apply(conn)  # must not raise
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"repos", "nodes", "edges"} <= tables


def test_node_repo_fk_cascades(conn):
    """Deleting a repos row cascades away its nodes (FK ON DELETE CASCADE)."""
    _apply(conn)
    conn.execute(
        "INSERT INTO repos (repo, updated_at) VALUES (?, ?)", ("o/r", "2026-01-01T00:00:00+00:00")
    )
    conn.execute("INSERT INTO nodes (repo, id, label) VALUES (?, ?, ?)", ("o/r", "n1", "f"))
    conn.commit()
    conn.execute("DELETE FROM repos WHERE repo = ?", ("o/r",))
    conn.commit()
    n = conn.execute("SELECT COUNT(*) AS n FROM nodes").fetchone()["n"]
    assert n == 0


def test_node_source_fk_cascades_edges(conn):
    """Deleting a source node directly cascades away its owned edges via the
    edges(repo, source) -> nodes FK. This is the load-bearing cascade behind
    invalidate_file's file-delete path; assert it explicitly with FK ON."""
    _apply(conn)
    conn.execute(
        "INSERT INTO repos (repo, updated_at) VALUES (?, ?)", ("o/r", "2026-01-01T00:00:00+00:00")
    )
    conn.execute("INSERT INTO nodes (repo, id, label) VALUES (?, ?, ?)", ("o/r", "n1", "src"))
    conn.execute("INSERT INTO nodes (repo, id, label) VALUES (?, ?, ?)", ("o/r", "n2", "tgt"))
    conn.execute(
        "INSERT INTO edges (repo, source, target, relation) VALUES (?, ?, ?, ?)",
        ("o/r", "n1", "n2", "calls"),
    )
    conn.commit()
    conn.execute("DELETE FROM nodes WHERE repo = ? AND id = ?", ("o/r", "n1"))
    conn.commit()
    edges = conn.execute("SELECT COUNT(*) AS n FROM edges").fetchone()["n"]
    assert edges == 0
