from scripts import db


def test_module_importable():
    assert hasattr(db, "get_connection")


import sqlite3
from scripts.db import get_connection


def test_get_connection_returns_sqlite_connection(tmp_store_path):
    conn = get_connection(str(tmp_store_path))
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_get_connection_enables_wal(tmp_store_path):
    conn = get_connection(str(tmp_store_path))
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    conn.close()


def test_get_connection_synchronous_normal(tmp_store_path):
    conn = get_connection(str(tmp_store_path))
    val = conn.execute("PRAGMA synchronous").fetchone()[0]
    assert val == 1
    conn.close()


def test_get_connection_foreign_keys_on(tmp_store_path):
    conn = get_connection(str(tmp_store_path))
    val = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert val == 1
    conn.close()


def test_get_connection_returns_dict_rows(tmp_store_path):
    conn = get_connection(str(tmp_store_path))
    conn.execute("CREATE TABLE t (a INTEGER, b TEXT)")
    conn.execute("INSERT INTO t VALUES (1, 'x')")
    row = conn.execute("SELECT * FROM t").fetchone()
    assert row["a"] == 1
    assert row["b"] == "x"
    conn.close()
