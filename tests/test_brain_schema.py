from pathlib import Path

from scripts.db import get_connection


def test_brain_schema_applies(tmp_path):
    sql = Path("db/brain.sql").read_text()
    db = tmp_path / "article.db"
    conn = get_connection(str(db))
    conn.executescript(sql)
    conn.commit()
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("articles", "captures", "syntheses"):
        assert t in tables
    conn.close()


def test_brain_tables_have_index_id(tmp_path):
    sql = Path("db/brain.sql").read_text()
    db = tmp_path / "article.db"
    conn = get_connection(str(db))
    conn.executescript(sql)
    for table in ("articles", "captures", "syntheses"):
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        assert "index_id" in cols, f"{table} missing index_id"
    conn.close()


def test_articles_has_source_hash(tmp_path):
    sql = Path("db/brain.sql").read_text()
    db = tmp_path / "article.db"
    conn = get_connection(str(db))
    conn.executescript(sql)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(articles)")}
    assert "source_hash" in cols
    assert "source_url" in cols
    assert "raw_path" in cols
    conn.close()
