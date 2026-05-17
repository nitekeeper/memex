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


def test_documents_key_has_unique_index(tmp_path):
    """Spec §5.2 / §6.4: documents_key_unique_idx is UNIQUE."""
    sql = Path("db/index.sql").read_text(encoding="utf-8")
    db = tmp_path / "index.db"
    conn = get_connection(str(db))
    conn.executescript(sql)
    row = conn.execute(
        "SELECT \"unique\" FROM pragma_index_list('documents') "
        "WHERE name = 'documents_key_unique_idx'"
    ).fetchone()
    conn.close()
    assert row is not None, "documents_key_unique_idx not found"
    assert row["unique"] == 1, "documents_key_unique_idx must be UNIQUE"


def test_documents_key_unique_rejects_duplicates(tmp_path):
    """Spec §6.4(a): two non-NULL rows sharing a key must fail."""
    import sqlite3

    import pytest

    sql = Path("db/index.sql").read_text(encoding="utf-8")
    db = tmp_path / "index.db"
    conn = get_connection(str(db))
    conn.executescript(sql)
    conn.commit()
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("a", "shared-key", "article", "brain", "articles", "1", "x", "system"),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
            "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("b", "shared-key", "article", "brain", "articles", "2", "y", "system"),
        )
        conn.commit()
    conn.close()


def test_documents_key_unique_allows_multiple_nulls(tmp_path):
    """Spec §6.4(a): NULL keys are distinct under SQLite UNIQUE semantics;
    unkeyed captures continue to work."""
    sql = Path("db/index.sql").read_text(encoding="utf-8")
    db = tmp_path / "index.db"
    conn = get_connection(str(db))
    conn.executescript(sql)
    conn.commit()
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("a", None, "capture", "brain", "captures", "1", "x", "system"),
    )
    conn.execute(
        "INSERT INTO documents (index_id, key, domain, store, table_name, row_id, "
        "searchable, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("b", None, "capture", "brain", "captures", "2", "y", "system"),
    )
    conn.commit()
    count = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
    conn.close()
    assert count == 2


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
