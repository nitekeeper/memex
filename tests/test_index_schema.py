import sqlite3
from pathlib import Path

from scripts.db import get_connection


def test_index_schema_applies_cleanly(tmp_path):
    sql = Path("db/index.sql").read_text(encoding="utf-8")
    db = tmp_path / "index.db"
    conn = get_connection(str(db))
    conn.executescript(sql)
    conn.commit()
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "documents" in tables
    assert "relations" in tables


def test_index_schema_has_fts5(tmp_path):
    sql = Path("db/index.sql").read_text(encoding="utf-8")
    db = tmp_path / "index.db"
    conn = get_connection(str(db))
    conn.executescript(sql)
    conn.commit()
    has_fts = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='documents_fts' AND type='table'"
    ).fetchone()
    conn.close()
    assert has_fts is not None


def test_index_documents_has_embedding_blob(tmp_path):
    sql = Path("db/index.sql").read_text(encoding="utf-8")
    db = tmp_path / "index.db"
    conn = get_connection(str(db))
    conn.executescript(sql)
    cur = conn.execute("PRAGMA table_info(documents)")
    cols = {r["name"]: r["type"] for r in cur.fetchall()}
    conn.close()
    assert cols.get("embedding") == "BLOB"
    assert cols.get("index_id") == "TEXT"


def test_relations_pk_composite(tmp_path):
    sql = Path("db/index.sql").read_text(encoding="utf-8")
    db = tmp_path / "index.db"
    conn = get_connection(str(db))
    conn.executescript(sql)
    conn.commit()
    # Inserting the same triple twice must fail due to composite PK.
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("a", "k1", "article", "brain", "articles", "1", "x", "system"),
    )
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("b", "k2", "article", "brain", "articles", "2", "y", "system"),
    )
    conn.execute(
        "INSERT INTO relations (from_index_id, to_index_id, rel_type) VALUES (?, ?, ?)",
        ("a", "b", "cites"),
    )
    import pytest

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO relations (from_index_id, to_index_id, rel_type) VALUES (?, ?, ?)",
            ("a", "b", "cites"),
        )
        conn.commit()
    conn.close()
