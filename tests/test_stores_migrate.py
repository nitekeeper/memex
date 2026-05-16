import pytest

from scripts import stores
from scripts.db import get_connection


def _make_store(tmp_memex_home, tmp_path, initial_sql="CREATE TABLE t (a INTEGER);"):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_init.sql").write_text(initial_sql)
    target = tmp_path / "alpha.db"
    stores.create_store("alpha", str(target), str(migrations_dir))
    return target, migrations_dir


def test_migrate_applies_new_files(tmp_memex_home, tmp_path):
    target, migrations_dir = _make_store(tmp_memex_home, tmp_path)
    (migrations_dir / "002_added.sql").write_text("CREATE TABLE u (b TEXT);")
    stores.migrate("alpha", str(migrations_dir))
    conn = get_connection(str(target))
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "u" in tables


def test_migrate_skips_already_applied(tmp_memex_home, tmp_path):
    target, migrations_dir = _make_store(tmp_memex_home, tmp_path)
    stores.migrate("alpha", str(migrations_dir))
    conn = get_connection(str(target))
    applied = [r["filename"] for r in conn.execute("SELECT filename FROM migrations ORDER BY id")]
    conn.close()
    assert applied == ["001_init.sql"]


def test_migrate_idempotent(tmp_memex_home, tmp_path):
    target, migrations_dir = _make_store(tmp_memex_home, tmp_path)
    (migrations_dir / "002_added.sql").write_text("CREATE TABLE u (b TEXT);")
    stores.migrate("alpha", str(migrations_dir))
    stores.migrate("alpha", str(migrations_dir))
    conn = get_connection(str(target))
    rows = conn.execute("SELECT COUNT(*) AS n FROM migrations").fetchone()
    conn.close()
    assert rows["n"] == 2


def test_migrate_unknown_store_raises(tmp_memex_home, tmp_path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    with pytest.raises(ValueError):
        stores.migrate("does-not-exist", str(migrations_dir))
