import pytest

from scripts import stores


@pytest.fixture
def store_with_table(bootstrapped_marker, tmp_path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_init.sql").write_text(
        "CREATE TABLE items ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "name TEXT NOT NULL, "
        "qty INTEGER NOT NULL DEFAULT 0"
        ");"
    )
    target = tmp_path / "alpha.db"
    stores.create_store("alpha", str(target), str(migrations_dir))
    return "alpha"


def test_insert_returns_row_with_id(store_with_table):
    row = stores.insert(store_with_table, "items", {"name": "widget", "qty": 5})
    assert row["id"] > 0
    assert row["name"] == "widget"
    assert row["qty"] == 5


def test_query_returns_list_of_dicts(store_with_table):
    stores.insert(store_with_table, "items", {"name": "a", "qty": 1})
    stores.insert(store_with_table, "items", {"name": "b", "qty": 2})
    rows = stores.query(store_with_table, "SELECT * FROM items ORDER BY name")
    assert len(rows) == 2
    assert rows[0]["name"] == "a"


def test_query_supports_params(store_with_table):
    stores.insert(store_with_table, "items", {"name": "a", "qty": 1})
    stores.insert(store_with_table, "items", {"name": "b", "qty": 99})
    rows = stores.query(store_with_table, "SELECT * FROM items WHERE qty > ?", (50,))
    assert len(rows) == 1
    assert rows[0]["name"] == "b"


def test_update_changes_rows(store_with_table):
    row = stores.insert(store_with_table, "items", {"name": "a", "qty": 1})
    stores.update(store_with_table, "items", row["id"], {"qty": 99})
    refetched = stores.query(store_with_table, "SELECT * FROM items WHERE id = ?", (row["id"],))
    assert refetched[0]["qty"] == 99


def test_delete_removes_row(store_with_table):
    row = stores.insert(store_with_table, "items", {"name": "a", "qty": 1})
    assert stores.delete(store_with_table, "items", row["id"]) is True
    refetched = stores.query(store_with_table, "SELECT * FROM items WHERE id = ?", (row["id"],))
    assert refetched == []


def test_delete_returns_false_when_missing(store_with_table):
    assert stores.delete(store_with_table, "items", 99999) is False


def test_query_unknown_store_raises(bootstrapped_marker):
    with pytest.raises(ValueError):
        stores.query("no-such-store", "SELECT 1")
