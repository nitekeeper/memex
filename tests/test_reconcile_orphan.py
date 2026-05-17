import pytest

from scripts import install, stores
from scripts.agents import data_steward
from scripts.db import get_connection, memex_home


def _seed_orphan(index_id: str, store: str = "no-store", table: str = "t", row_id: str = "1"):
    # Per-call distinct key: documents.key is UNIQUE (spec §6.4); seeding
    # multiple orphans in one test would otherwise collide on a shared key.
    conn = get_connection(str(memex_home() / "index.db"))
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (index_id, f"key-{index_id}", "article", store, table, row_id, "txt", "librarian-1"),
    )
    conn.commit()
    conn.close()


def _seed_link_missing_orphan(index_id: str, store: str, table: str):
    """Seed a Class-B orphan: documents row with row_id = '' (link never written).

    documents.row_id is TEXT NOT NULL, so the empty-string form is the only
    reachable representation of a missing link under the current schema.
    """
    conn = get_connection(str(memex_home() / "index.db"))
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, searchable, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (index_id, f"key-{index_id}", "article", store, table, "", "txt", "librarian-1"),
    )
    conn.commit()
    conn.close()


def _register_store_with_row(tmp_path, store_name="test-store"):
    md = tmp_path / "m"
    md.mkdir()
    (md / "001.sql").write_text(
        "CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, index_id TEXT, body TEXT);"
    )
    stores.create_store(store_name, str(tmp_path / "ts.db"), str(md))
    return stores.insert(store_name, "items", {"index_id": "idx-target", "body": "x"})


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


# --- OrphanNotFoundError -----------------------------------------------------


def test_reconcile_raises_orphan_not_found_for_unknown_index_id(tmp_memex_home):
    install.run()
    with pytest.raises(data_steward.OrphanNotFoundError) as exc_info:
        data_steward.reconcile_orphan("idx-does-not-exist", action="delete-index")
    assert exc_info.value.index_id == "idx-does-not-exist"


def test_orphan_not_found_error_carries_index_id_attribute(tmp_memex_home):
    install.run()
    err = data_steward.OrphanNotFoundError("idx-x")
    assert err.index_id == "idx-x"
    assert "idx-x" in str(err)


# --- repair action -----------------------------------------------------------


def test_reconcile_repair_backfills_row_id_when_target_exists(tmp_memex_home, tmp_path):
    install.run()
    target = _register_store_with_row(tmp_path, store_name="test-store")
    _seed_link_missing_orphan("idx-r1", store="test-store", table="items")

    result = data_steward.reconcile_orphan(
        "idx-r1", action="repair", repair_row_id=str(target["id"])
    )

    conn = get_connection(str(memex_home() / "index.db"))
    row = conn.execute("SELECT row_id FROM documents WHERE index_id = ?", ("idx-r1",)).fetchone()
    conn.close()
    assert row["row_id"] == str(target["id"])
    assert result["action"] == "repair"
    assert result["index_id"] == "idx-r1"
    assert result["row_id"] == str(target["id"])


def test_reconcile_repair_requires_repair_row_id_kwarg(tmp_memex_home, tmp_path):
    install.run()
    _register_store_with_row(tmp_path, store_name="test-store")
    _seed_link_missing_orphan("idx-r2", store="test-store", table="items")

    with pytest.raises(ValueError, match="repair_row_id"):
        data_steward.reconcile_orphan("idx-r2", action="repair")


def test_reconcile_repair_raises_when_target_row_missing(tmp_memex_home, tmp_path):
    install.run()
    _register_store_with_row(tmp_path, store_name="test-store")
    _seed_link_missing_orphan("idx-r3", store="test-store", table="items")

    with pytest.raises(ValueError, match="target row"):
        data_steward.reconcile_orphan("idx-r3", action="repair", repair_row_id="99999")


def test_reconcile_repair_raises_when_store_not_registered(tmp_memex_home):
    install.run()
    _seed_link_missing_orphan("idx-r4", store="no-such-store", table="items")

    with pytest.raises(ValueError, match="store"):
        data_steward.reconcile_orphan("idx-r4", action="repair", repair_row_id="1")


def test_reconcile_repair_raises_orphan_not_found_when_row_id_already_populated(
    tmp_memex_home, tmp_path
):
    install.run()
    target = _register_store_with_row(tmp_path, store_name="test-store")
    # Seed with row_id already populated — not the orphan class `repair` handles.
    _seed_orphan("idx-r5", store="test-store", table="items", row_id=str(target["id"]))

    with pytest.raises(data_steward.OrphanNotFoundError):
        data_steward.reconcile_orphan("idx-r5", action="repair", repair_row_id=str(target["id"]))


def test_reconcile_repair_writes_audit_log(tmp_memex_home, tmp_path):
    install.run()
    target = _register_store_with_row(tmp_path, store_name="test-store")
    _seed_link_missing_orphan("idx-r6", store="test-store", table="items")

    data_steward.reconcile_orphan("idx-r6", action="repair", repair_row_id=str(target["id"]))

    log_path = memex_home() / "audits" / "reconciliation-log.md"
    content = log_path.read_text()
    assert "idx-r6" in content
    assert "action=repair" in content
    assert f"row_id={target['id']}" in content
