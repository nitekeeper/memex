import sqlite3
from pathlib import Path

import pytest

from scripts.db import get_connection
from scripts import roles, agents


@pytest.fixture
def agents_db_with_role(tmp_path):
    p = tmp_path / "agents.db"
    sql = Path("db/agents.sql").read_text()
    conn = get_connection(str(p))
    conn.executescript(sql)
    conn.commit()
    conn.close()
    role = roles.create_role(str(p), "Librarian", "Indexing authority")
    return str(p), role["id"]


def test_create_agent(agents_db_with_role):
    db, role_id = agents_db_with_role
    a = agents.create_agent(db, "lib-1", "Dr. Test", role_id, "profile text")
    assert a["id"] == "lib-1"
    assert a["name"] == "Dr. Test"
    assert a["role_id"] == role_id
    assert a["profile"] == "profile text"


def test_get_agent(agents_db_with_role):
    db, role_id = agents_db_with_role
    agents.create_agent(db, "lib-1", "X", role_id, "p")
    a = agents.get_agent(db, "lib-1")
    assert a["name"] == "X"


def test_get_agent_returns_none_when_missing(agents_db_with_role):
    db, _ = agents_db_with_role
    assert agents.get_agent(db, "nope") is None


def test_list_agents_ordered_by_id(agents_db_with_role):
    db, role_id = agents_db_with_role
    agents.create_agent(db, "z", "Z", role_id, "p")
    agents.create_agent(db, "a", "A", role_id, "p")
    listed = agents.list_agents(db)
    assert [a["id"] for a in listed] == ["a", "z"]


def test_update_agent_profile(agents_db_with_role):
    db, role_id = agents_db_with_role
    agents.create_agent(db, "lib-1", "X", role_id, "original")
    agents.update_agent(db, "lib-1", profile="updated")
    a = agents.get_agent(db, "lib-1")
    assert a["profile"] == "updated"


def test_delete_agent(agents_db_with_role):
    db, role_id = agents_db_with_role
    agents.create_agent(db, "lib-1", "X", role_id, "p")
    assert agents.delete_agent(db, "lib-1") is True
    assert agents.get_agent(db, "lib-1") is None


def test_create_agent_requires_valid_role(agents_db_with_role):
    db, _ = agents_db_with_role
    with pytest.raises(sqlite3.IntegrityError):
        agents.create_agent(db, "x", "X", 99999, "p")


def test_list_by_role(agents_db_with_role):
    db, role_id = agents_db_with_role
    other_role = roles.create_role(db, "Other", "x")
    agents.create_agent(db, "a", "A", role_id, "p")
    agents.create_agent(db, "b", "B", other_role["id"], "p")
    listed = agents.list_by_role(db, role_id)
    assert [a["id"] for a in listed] == ["a"]
