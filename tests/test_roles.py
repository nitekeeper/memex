import sqlite3
from pathlib import Path

import pytest

from scripts.db import get_connection
from scripts import roles


@pytest.fixture
def agents_db(tmp_path):
    """Disposable agents.db with schema applied."""
    p = tmp_path / "agents.db"
    sql = Path("db/agents.sql").read_text()
    conn = get_connection(str(p))
    conn.executescript(sql)
    conn.commit()
    conn.close()
    return str(p)


def test_create_role(agents_db):
    r = roles.create_role(agents_db, "Librarian", "Indexing authority")
    assert r["id"] > 0
    assert r["name"] == "Librarian"
    assert r["description"] == "Indexing authority"


def test_get_role(agents_db):
    created = roles.create_role(agents_db, "Archivist", "Custodian of history")
    fetched = roles.get_role(agents_db, created["id"])
    assert fetched["id"] == created["id"]
    assert fetched["name"] == "Archivist"


def test_get_role_returns_none_when_missing(agents_db):
    assert roles.get_role(agents_db, 9999) is None


def test_list_roles_orders_by_name(agents_db):
    roles.create_role(agents_db, "Zeta", "z")
    roles.create_role(agents_db, "Alpha", "a")
    roles.create_role(agents_db, "Mu", "m")
    listed = roles.list_roles(agents_db)
    assert [r["name"] for r in listed] == ["Alpha", "Mu", "Zeta"]


def test_search_roles_matches_name_or_description(agents_db):
    roles.create_role(agents_db, "Librarian", "catalogs documents")
    roles.create_role(agents_db, "Archivist", "preserves history")
    results = roles.search_roles(agents_db, "catalog")
    assert len(results) == 1
    assert results[0]["name"] == "Librarian"


def test_update_role_partial(agents_db):
    r = roles.create_role(agents_db, "X", "original")
    roles.update_role(agents_db, r["id"], description="updated")
    fetched = roles.get_role(agents_db, r["id"])
    assert fetched["description"] == "updated"
    assert fetched["name"] == "X"


def test_delete_role(agents_db):
    r = roles.create_role(agents_db, "X", "y")
    assert roles.delete_role(agents_db, r["id"]) is True
    assert roles.get_role(agents_db, r["id"]) is None


def test_delete_role_returns_false_when_missing(agents_db):
    assert roles.delete_role(agents_db, 9999) is False


def test_create_role_unique_name_raises(agents_db):
    roles.create_role(agents_db, "Duplicate", "first")
    with pytest.raises(sqlite3.IntegrityError):
        roles.create_role(agents_db, "Duplicate", "second")
