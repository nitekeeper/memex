import sqlite3
from pathlib import Path

import pytest

from scripts.db import get_connection


def test_agents_schema_applies_cleanly(tmp_store_path):
    sql = Path("db/agents.sql").read_text()
    conn = get_connection(str(tmp_store_path))
    conn.executescript(sql)
    conn.commit()
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "roles" in tables
    assert "agents" in tables
    conn.close()


def test_agents_role_fk_enforced(tmp_store_path):
    sql = Path("db/agents.sql").read_text()
    conn = get_connection(str(tmp_store_path))
    conn.executescript(sql)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO agents (id, name, role_id, profile) VALUES (?, ?, ?, ?)",
            ("a1", "x", 999, "profile"),
        )
        conn.commit()
    conn.close()
