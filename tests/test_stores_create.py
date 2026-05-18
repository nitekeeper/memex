import pytest

from scripts import registry, stores
from scripts.db import get_connection


def test_create_store_creates_file(bootstrapped_marker, tmp_path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_init.sql").write_text("CREATE TABLE t (a INTEGER);")
    target = tmp_path / "alpha.db"
    stores.create_store("alpha", str(target), str(migrations_dir))
    assert target.exists()


def test_create_store_runs_migrations(bootstrapped_marker, tmp_path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_init.sql").write_text("CREATE TABLE t (a INTEGER, b TEXT);")
    target = tmp_path / "alpha.db"
    stores.create_store("alpha", str(target), str(migrations_dir))
    conn = get_connection(str(target))
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "t" in tables
    assert "migrations" in tables


def test_create_store_records_applied_migrations(bootstrapped_marker, tmp_path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_init.sql").write_text("CREATE TABLE t (a INTEGER);")
    (migrations_dir / "002_more.sql").write_text("CREATE TABLE u (b TEXT);")
    target = tmp_path / "alpha.db"
    stores.create_store("alpha", str(target), str(migrations_dir))
    conn = get_connection(str(target))
    applied = [
        r["filename"] for r in conn.execute("SELECT filename FROM migrations ORDER BY filename")
    ]
    conn.close()
    assert applied == ["001_init.sql", "002_more.sql"]


def test_create_store_registers_in_registry(bootstrapped_marker, tmp_path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_init.sql").write_text("CREATE TABLE t (a INTEGER);")
    target = tmp_path / "alpha.db"
    stores.create_store("alpha", str(target), str(migrations_dir))
    rec = registry.get_store("alpha")
    assert rec is not None
    assert rec["path"] == str(target)


def test_create_store_refuses_existing_name(bootstrapped_marker, tmp_path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "001_init.sql").write_text("CREATE TABLE t (a INTEGER);")
    stores.create_store("alpha", str(tmp_path / "a.db"), str(migrations_dir))
    with pytest.raises(ValueError):
        stores.create_store("alpha", str(tmp_path / "b.db"), str(migrations_dir))


def test_create_store_applies_migrations_in_lexical_order(bootstrapped_marker, tmp_path):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "002_second.sql").write_text("CREATE TABLE b (x INTEGER);")
    (migrations_dir / "001_first.sql").write_text("CREATE TABLE a (x INTEGER);")
    (migrations_dir / "003_third.sql").write_text("ALTER TABLE a ADD COLUMN y TEXT;")
    target = tmp_path / "alpha.db"
    stores.create_store("alpha", str(target), str(migrations_dir))
    conn = get_connection(str(target))
    applied = [r["filename"] for r in conn.execute("SELECT filename FROM migrations ORDER BY id")]
    conn.close()
    assert applied == ["001_first.sql", "002_second.sql", "003_third.sql"]
