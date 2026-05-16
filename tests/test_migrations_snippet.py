from pathlib import Path


def test_migrations_snippet_exists():
    p = Path("db/migrations_table.sql")
    assert p.exists()


def test_migrations_snippet_uses_if_not_exists():
    sql = Path("db/migrations_table.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS migrations" in sql


def test_migrations_snippet_columns():
    sql = Path("db/migrations_table.sql").read_text()
    for col in ("filename", "applied_at"):
        assert col in sql
