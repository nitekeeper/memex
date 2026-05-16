import pytest

from scripts import install
from scripts.agents import data_steward
from scripts.db import get_connection, memex_home


def _seed_orphan(index_id: str, store: str = "no-store", table: str = "t", row_id: str = "1"):
    conn = get_connection(str(memex_home() / "index.db"))
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (index_id, "k", "article", store, table, row_id, "txt", "librarian-1"),
    )
    conn.commit()
    conn.close()


def test_reconcile_delete_index_removes_documents_row(tmp_memex_home):
    install.run()
    _seed_orphan("idx-o1")

    data_steward.reconcile_orphan("idx-o1", action="delete-index")

    conn = get_connection(str(memex_home() / "index.db"))
    row = conn.execute("SELECT * FROM documents WHERE index_id = ?", ("idx-o1",)).fetchone()
    conn.close()
    assert row is None


def test_reconcile_delete_index_also_removes_relations(tmp_memex_home):
    install.run()
    _seed_orphan("idx-o2")
    _seed_orphan("idx-o2-target")
    conn = get_connection(str(memex_home() / "index.db"))
    conn.execute(
        "INSERT INTO relations (from_index_id, to_index_id, rel_type) VALUES (?, ?, ?)",
        ("idx-o2", "idx-o2-target", "cites"),
    )
    conn.commit()
    conn.close()

    data_steward.reconcile_orphan("idx-o2", action="delete-index")

    conn = get_connection(str(memex_home() / "index.db"))
    rels = conn.execute(
        "SELECT * FROM relations WHERE from_index_id = ? OR to_index_id = ?", ("idx-o2", "idx-o2")
    ).fetchall()
    conn.close()
    assert rels == []


def test_reconcile_note_leaves_data_unchanged(tmp_memex_home):
    install.run()
    _seed_orphan("idx-o3")

    data_steward.reconcile_orphan("idx-o3", action="note", note_text="acknowledged: known orphan")

    conn = get_connection(str(memex_home() / "index.db"))
    row = conn.execute("SELECT * FROM documents WHERE index_id = ?", ("idx-o3",)).fetchone()
    conn.close()
    assert row is not None  # still there


def test_reconcile_unknown_action_raises(tmp_memex_home):
    install.run()
    _seed_orphan("idx-o4")
    with pytest.raises(ValueError):
        data_steward.reconcile_orphan("idx-o4", action="explode")
