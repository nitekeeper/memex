import sqlite3

import pytest

from scripts import db
from scripts.db import get_connection, memex_home, safe_identifier


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


class TestSafeIdentifier:
    """safe_identifier() is the only sanctioned way to interpolate SQL
    identifiers in this codebase. These tests pin its contract."""

    @pytest.mark.parametrize(
        "name",
        [
            "articles",
            "test_table",
            "_underscore_start",
            "TableCamelCase",
            "t1",
            "snake_case_with_99_digits",
        ],
    )
    def test_accepts_valid_identifiers(self, name):
        assert safe_identifier(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "1starts_with_digit",
            "has-dash",
            "has space",
            "has;semicolon",
            "DROP TABLE users",
            "table; DROP TABLE users--",
            "",
            "with.dot",
            "with'quote",
            'with"doublequote',
            "with(paren",
            "unicode-é",
        ],
    )
    def test_rejects_invalid_identifiers(self, name):
        with pytest.raises(ValueError, match="invalid SQL identifier"):
            safe_identifier(name)

    def test_rejects_non_string_types(self):
        with pytest.raises(ValueError, match="must be str"):
            safe_identifier(123)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="must be str"):
            safe_identifier(None)  # type: ignore[arg-type]

    def test_injection_payload_blocked(self):
        """The whole point: a classic injection payload must not pass."""
        for payload in [
            "users; DROP TABLE users; --",
            "1 OR 1=1",
            "users UNION SELECT * FROM secrets",
        ]:
            with pytest.raises(ValueError):
                safe_identifier(payload)
