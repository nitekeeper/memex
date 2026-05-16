import sqlite3

from scripts import db
from scripts.db import get_connection, memex_home


def test_module_importable():
    assert hasattr(db, "get_connection")


def test_get_connection_returns_sqlite_connection(conn):
    assert isinstance(conn, sqlite3.Connection)


def test_get_connection_accepts_path_object(tmp_store_path):
    # F7: db_path is typed str | os.PathLike[str]; pass Path directly.
    c = get_connection(tmp_store_path)
    try:
        assert isinstance(c, sqlite3.Connection)
    finally:
        c.close()


def test_get_connection_enables_wal(conn):
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_get_connection_synchronous_normal(conn):
    val = conn.execute("PRAGMA synchronous").fetchone()[0]
    assert val == 1  # NORMAL


def test_get_connection_foreign_keys_on(conn):
    val = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert val == 1  # ON


def test_get_connection_returns_dict_rows(conn):
    conn.execute("CREATE TABLE t (a INTEGER, b TEXT)")
    conn.execute("INSERT INTO t VALUES (1, 'x')")
    row = conn.execute("SELECT * FROM t").fetchone()
    assert row["a"] == 1
    assert row["b"] == "x"


def test_memex_home_respects_env(tmp_memex_home):
    assert memex_home() == tmp_memex_home


def test_memex_home_defaults_to_user_home(monkeypatch, tmp_path):
    monkeypatch.delenv("MEMEX_HOME", raising=False)
    fake_home = tmp_path / "userhome"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    assert memex_home() == fake_home / ".memex"
